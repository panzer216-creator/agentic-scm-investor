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
import google.generativeai as genai

# --- [Configuration] ---
SHEET_ID = '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0'
NEW_HEADERS = ["Date", "Theme/Sector", "Stock Name (Code)", "Entry Price", "Stop Loss (-10%)", "Reasoning", "Action", "Result"]
TARGET_TAB = "Trading_Log"

# --- [Global Initialization] ---
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [Module D: Google Sheets Logic - 불렛푸르프 보완] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    # 1. 시트 목록 확인
    spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_names = [s['properties']['title'] for s in sheets]
    
    # 2. 'Trading_Log' 탭이 없으면 첫 번째 탭의 이름을 변경
    if TARGET_TAB not in sheet_names:
        first_sheet_id = sheets[0]['properties']['sheetId']
        batch_update_request = {
            'requests': [{
                'updateSheetProperties': {
                    'properties': {'sheetId': first_sheet_id, 'title': TARGET_TAB},
                    'fields': 'title'
                }
            }]
        }
        sheet.batchUpdate(spreadsheetId=SHEET_ID, body=batch_update_request).execute()
        print(f"시트 이름을 '{TARGET_TAB}'으로 변경 완료.")
        time.sleep(2) # 구글 서버 동기화를 위한 대기
    
    # 3. 헤더 검사 및 초기화 (따옴표를 추가하여 범위 해석 오류 방지)
    range_name = f"'{TARGET_TAB}'!A1:H1"
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    current_header = result.get('values', [[]])[0]
    
    if current_header != NEW_HEADERS:
        sheet.values().clear(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID, range=range_name,
            valueInputOption="RAW", body={"values": [NEW_HEADERS]}
        ).execute()
        print("헤더 구성 완료.")
    
    return sheet

# --- [Module A: Gemini Intelligent Filter] ---
def filter_etfs_with_gemini(etf_names):
    prompt = f"다음 ETF 중 테마형만 골라 콤마로 구분해줘: {etf_names}"
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        return response.text if response else None
    except:
        return None

# --- [Module C: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if len(df) < 20: return None
        df = df.tail(20)
        
        high_price = df['High'].max()
        tr = pd.concat([df['High'] - df['Low'], abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        
        entry = max(vwap_5d.iloc[-1], high_price - (1.5 * atr))
        return round(entry), round(entry * 0.90)
    except:
        return None

# --- [Module E: Telegram with Retry] ---
def send_telegram_with_retry(token, chat_id, text):
    for attempt in range(3):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                                 data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            resp.raise_for_status()
            return True
        except:
            time.sleep(2 ** attempt)
    return False

# --- [Main Execution Flow] ---
def main():
    try:
        sheet_service = init_google_sheets()
        
        # 샘플 데이터 가동
        stocks = [("삼성전기", "009150", "반도체"), ("에이스테크", "088800", "5G")]
        trading_data = []
        telegram_msg = "🚨 <b>[에이전트 MTS 지시서]</b>\n\n"
        
        for name, code, theme in stocks:
            res = calculate_trading_signals(code)
            if not res: continue
            entry, stop = res
            name_esc = html.escape(name)
            
            trading_data.append([datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, "SCM 기반 분석", "대기", "N/A"])
            telegram_msg += f"🎯 <b>{name_esc}</b>\n- 타점: {entry:,}원\n- 손절: {stop:,}원\n\n"

        if trading_data:
            sheet_service.values().append(
                spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": trading_data}
            ).execute()
            send_telegram_with_retry(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg)
            print("공정 완료: 시트 기록 및 텔레그램 발송 성공")
            
    except Exception as e:
        print(f"공정 중단 에러: {e}")

if __name__ == "__main__":
    main()
