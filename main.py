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
SEED_TAB = "Seed_Data_414"
TARGET_TAB = "Trading_Log"

# [4/14 주도주 마스터 데이터 - 종목명과 바코드(코드) 매핑]
MASTER_RESOURCES = [
    ("삼성전자", "005930"), ("SK하이닉스", "000660"), ("한미반도체", "042700"), ("현대차", "005380"), 
    ("알테오젠", "191150"), ("셀트리온", "068270"), ("기아", "000270"), ("HLB", "028300"), 
    ("에코프로머티", "450080"), ("이수페타시스", "007660"), ("테크윙", "089030"), ("제주반도체", "080220"), 
    ("가온칩스", "397120"), ("오픈엣지테크놀로지", "394280"), ("에이직랜드", "445090"), ("유한양행", "000100")
]

# --- [2. Google Sheets Logic] ---
def get_service():
    creds_dict = json.loads(os.environ.get('GOOGLE_SHEETS_CREDENTIALS'))
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds).spreadsheets()

def sync_master_data(service):
    # 창고에 바코드(코드)가 포함된 정확한 리스트를 다시 채웁니다.
    header = [["Date", "Stock Name", "Ticker"]]
    rows = [[ "2026-04-14", name, code] for name, code in MASTER_RESOURCES]
    service.values().clear(spreadsheetId=SHEET_ID, range=f"'{SEED_TAB}'!A:C").execute()
    service.values().update(spreadsheetId=SHEET_ID, range=f"'{SEED_TAB}'!A1", valueInputOption="RAW", body={"values": header + rows}).execute()
    return rows

# --- [3. Module: Technical Analysis with Code] ---
def analyze_with_ticker(name, ticker):
    time.sleep(1) # 네이버 서버 보호용 리드타임
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        # 이름이 아닌 '숫자 코드'로 데이터 요청 (가장 안정적)
        df = fdr.DataReader(ticker, start_date)
        if df is None or df.empty: return f"❌ {name}: 로드 실패"
        
        df = df.tail(20)
        high = df['High'].max()
        # 5일 가중평균단가(VWAP) 및 14일 변동성(ATR) 산출
        vwap = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        entry = max(vwap.iloc[-1], high - (1.5 * atr))
        return {"entry": round(entry), "stop": round(entry * 0.9), "msg": f"✅ {name}: 분석 완료"}
    except Exception as e:
        return f"❌ {name}: 오류({str(e)[:10]})"

# --- [4. Main Workflow] ---
def main():
    token, chat_id = os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID']
    try:
        service = get_service()
        # 1. 마스터 데이터 동기화 (바코드 부착)
        master_rows = sync_master_data(service)
        
        trading_data, audit_logs = [], []
        telegram_msg = "🚨 <b>[V2.0 바코드 기반 복구 리포트]</b>\n\n"

        # 2. 코드(Ticker) 기반 정밀 가공
        for date, name, ticker in master_rows:
            result = analyze_with_ticker(name, ticker)
            if isinstance(result, dict):
                entry, stop = result['entry'], result['stop']
                trading_data.append([date, "V2.0복구", f"{name}({ticker})", entry, stop, "코드 기반 정밀분석", "대기", "N/A"])
                telegram_msg += f"🎯 <b>{name}</b>\n- 타점: {entry:,}원 | 손절: {stop:,}원\n\n"
                audit_logs.append(result['msg'])
            else:
                audit_logs.append(result)

        # 3. 결과 출하
        if trading_data:
            service.values().append(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}).execute()
        
        final_report = telegram_msg + "\n------------------\n🔍 <b>공정 수율 보고</b>\n" + "\n".join(audit_logs)
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": final_report, "parse_mode": "HTML"})
        
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": f"❌ 시스템 중단: {e}"})

if __name__ == "__main__":
    main()
