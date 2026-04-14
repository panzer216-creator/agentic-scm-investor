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
MASTER_TAB = "Seed_Data_414" 
TARGET_TAB = "Trading_Log"   

# --- [2. Google Sheets Logic] ---
def get_service():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def get_master_data(service):
    # 시트에서 종목 리스트 동적 로드 (하드코딩 완전 배제)
    result = service.values().get(spreadsheetId=SHEET_ID, range=f"'{MASTER_TAB}'!A2:C").execute()
    return result.get('values', [])

# --- [3. Pricing & QC (Overshoot) Logic] ---
def analyze_stock(category, name, ticker):
    time.sleep(1) # 서버 부하 방지 (리드타임)
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(ticker, start_date)
        if df is None or df.empty: return None
        
        current_price = int(df['Close'].iloc[-1])
        df_tail = df.tail(20)
        
        # VWAP 및 ATR 기반 타점 계산
        vwap = (df_tail['Close'] * df_tail['Volume']).rolling(5).sum() / df_tail['Volume'].rolling(5).sum()
        tr = pd.concat([df_tail['High']-df_tail['Low'], abs(df_tail['High']-df_tail['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        entry = round(max(vwap.iloc[-1], df_tail['High'].max() - (1.5 * atr)))
        stop = round(entry * 0.90)
        gap = round(((entry - current_price) / current_price) * 100, 2)
        
        # [핵심] 오버슈팅(과열) 감지 로직
        is_overshooting = current_price > (entry + (2.0 * atr))
        
        if is_overshooting:
            action = "⚠️ 과열(Overshoot)"
            reason = "타점 대비 2ATR 이상 초과"
        elif current_price >= entry:
            action = "🚀 매수(Buy)"
            reason = "타점 돌파 및 추세 확인"
        else:
            action = "⏳ 관망(Wait)"
            reason = f"타점까지 {gap}% 이격"
            
        return {
            "category": category, "name": name, "ticker": ticker,
            "current": current_price, "entry": entry, "stop": stop,
            "gap": gap, "action": action, "reason": reason
        }
    except Exception as e:
        print(f"[{name}] 분석 에러: {e}")
        return None

# --- [4. Main Workflow] ---
def main():
    token, chat_id = os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID']
    try:
        service = get_service()
        master_list = get_master_data(service)
        
        if not master_list:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": "⚠️ 원자재 창고가 비어있습니다."})
            return

        trading_data = []
        telegram_msg = "🚨 <b>[V2.3 시트 자립형 통합 지시서]</b>\n"
        telegram_msg += "<i>(전략 ETF 및 산업군 대장주 전수조사)</i>\n\n"

        for row in master_list:
            if len(row) < 3: continue
            category, name, ticker = row[0], row[1], row[2]
            
            res = analyze_stock(category, name, ticker)
            if not res: continue
            
            # 텔레그램 메시지 구성
            telegram_msg += f"📦 <b>[{res['category']}] {res['name']} ({res['ticker']})</b>\n"
            telegram_msg += f"- 현재가: {res['current']:,}원\n"
            telegram_msg += f"- 타점: <b>{res['entry']:,}원</b> (Gap: {res['gap']}%)\n"
            telegram_msg += f"📍 <b>판정: {res['action']}</b>\n\n"
            
            # 구글 시트 적재용 데이터
            trading_data.append([
                datetime.now().strftime("%Y-%m-%d"), res['category'], res['name'], 
                res['current'], res['entry'], res['stop'], res['reason'], res['action']
            ])

        # 출하 처리 (시트 기록 및 텔레그램 발송)
        if trading_data:
            service.values().append(
                spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", 
                valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}
            ).execute()
            
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": telegram_msg, "parse_mode": "HTML"})
            print("V2.3 공정 정상 완료")

    except Exception as e:
        print(f"시스템 에러: {e}")

if __name__ == "__main__":
    main()
