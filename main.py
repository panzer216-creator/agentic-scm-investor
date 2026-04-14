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
SOURCE_TAB = "Seed_Data_414"
TARGET_TAB = "Trading_Log"

# --- [2. Google Sheets Logic] ---
def get_service():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def get_stock_list_from_sheet(service):
    # Seed_Data_414 탭의 B열(종목명)을 50개 읽어옴
    range_name = f"'{SOURCE_TAB}'!B2:B51"
    result = service.values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    values = result.get('values', [])
    return [row[0] for row in values if row]

# --- [3. Module: Pricing Logic with Audit] ---
def calculate_signals_with_log(name):
    time.sleep(1) # 네이버 부하 방지
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        # FinanceDataReader가 종목명으로 시세를 제대로 가져오는지 확인
        df = fdr.DataReader(name, start_date)
        if df is None or df.empty: return f"❌ {name}: 데이터 로드 실패(Empty)"
        if len(df) < 15: return f"❌ {name}: 데이터 부족({len(df)}일)"
        
        df = df.tail(20)
        high_price = df['High'].max()
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        entry = max(vwap_5d.iloc[-1], high_price - (1.5 * atr))
        return {
            "entry": round(entry),
            "stop": round(entry * 0.90),
            "msg": f"✅ {name}: 분석 성공"
        }
    except Exception as e:
        return f"❌ {name}: 에러({str(e)[:15]})"

# --- [4. Main Workflow] ---
def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    try:
        service = get_service()
        stock_names = get_stock_list_from_sheet(service)
        
        if not stock_names:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": "⚠️ [공정 중단] 시트에서 종목 리스트를 읽지 못했습니다."})
            return

        trading_data = []
        audit_logs = []
        telegram_msg = "🚨 <b>[V1.9.1 자립형 공정 감사 리포트]</b>\n\n"
        
        # 상위 15개 종목 정밀 분석
        for name in stock_names[:15]:
            result = calculate_signals_with_log(name)
            
            if isinstance(result, dict): # 성공 시
                entry, stop = result['entry'], result['stop']
                trading_data.append([datetime.now().strftime("%Y-%m-%d"), "시트기반", name, entry, stop, "자립형 테스트", "대기", "N/A"])
                telegram_msg += f"🎯 <b>{html.escape(name)}</b>\n- 타점: {entry:,}원 | 손절: {stop:,}원\n\n"
                audit_logs.append(result['msg'])
            else: # 실패 시 사유 기록
                audit_logs.append(result)

        # 텔레그램으로 최종 보고 (성공/실패 상관없이 무조건 발송)
        final_report = telegram_msg + "\n------------------\n🔍 <b>공정 상세 로그 (Top 15)</b>\n" + "\n".join(audit_logs)
        
        if trading_data:
            service.values().append(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}).execute()
        
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": final_report, "parse_mode": "HTML"})
        print("공정 완료 및 리포트 발송 성공")
            
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": f"❌ 시스템 중단: {e}"})

if __name__ == "__main__":
    main()
