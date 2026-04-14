import os
import json
import time
import html
import pandas as pd
import FinanceDataReader as fdr
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- [1. Configuration] ---
SHEET_ID = '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0'
SOURCE_TAB = "Seed_Data_414"  # 원자재 창고
TARGET_TAB = "Trading_Log"    # 출하대

# --- [2. Google Sheets Logic] ---
def get_service():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def get_stock_list_from_sheet(service):
    # Seed_Data_414 탭의 B열(종목명)을 읽어옴
    range_name = f"'{SOURCE_TAB}'!B2:B51"
    result = service.values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    values = result.get('values', [])
    return [row[0] for row in values if row]

# --- [3. Module: Pricing Logic with Safety Buffer] ---
def calculate_signals(name):
    # 네이버 서버 부하 방지 (1초 대기)
    time.sleep(1)
    
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        # 네이버 소스를 통한 가격 데이터 로드
        df = fdr.DataReader(name, start_date)
        if df is None or len(df) < 15: return None
        
        df = df.tail(20)
        high_price = df['High'].max()
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        entry_target = max(vwap_5d.iloc[-1], high_price - (1.5 * atr))
        return round(entry_target), round(entry_target * 0.90)
    except Exception as e:
        print(f"⚠️ {name} 분석 실패: {e}")
        return None

# --- [4. Main Workflow] ---
def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    try:
        service = get_service()
        
        # 1. 시트에서 원자재(종목 리스트) 로드
        stock_names = get_stock_list_from_sheet(service)
        if not stock_names:
            print("원자재 창고가 비어있습니다.")
            return

        trading_data = []
        telegram_msg = "🚨 <b>[V1.9 시트 기반 자립형 리포트]</b>\n"
        telegram_msg += f"<i>({SOURCE_TAB} 리스트 분석 결과)</i>\n\n"
        
        # 2. 상위 15개 종목에 대해서만 우선 정밀 가공 (부하 관리)
        for name in stock_names[:15]:
            res = calculate_signals(name)
            if not res: continue
            
            entry, stop = res
            trading_data.append([
                datetime.now().strftime("%Y-%m-%d"), "시트기반", name, entry, stop, "자립형 공정 테스트", "대기", "N/A"
            ])
            telegram_msg += f"🎯 <b>{html.escape(name)}</b>\n- 타점: {entry:,}원 | 손절: {stop:,}원\n\n"

        # 3. 결과 출하
        if trading_data:
            service.values().append(
                spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}
            ).execute()
            
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={"chat_id": chat_id, "text": telegram_msg, "parse_mode": "HTML"})
            print("공정 완료")
        else:
            print("타점 조건 충족 종목 없음")
            
    except Exception as e:
        print(f"시스템 중단: {e}")

if __name__ == "__main__":
    main()
