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

# --- [1. Configuration] ---
SHEET_ID = '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0'
TARGET_TAB = "Trading_Log"
NEW_HEADERS = ["Date", "Theme/Sector", "Stock Name (Code)", "Entry Price", "Stop Loss (-10%)", "Reasoning", "Action", "Result"]

# --- [2. Global Initialization] ---
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [3. Module: Google Sheets Logic] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    # 시트 목록 확인 및 탭 이름 자동 관리
    spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_names = [s['properties']['title'] for s in sheets]
    
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
        time.sleep(1)
    
    # 헤더 무결성 검사 및 초기화
    range_name = f"'{TARGET_TAB}'!A1:H1"
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    current_header = result.get('values', [[]])[0]
    
    if current_header != NEW_HEADERS:
        sheet.values().clear(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID, range=range_name,
            valueInputOption="RAW", body={"values": [NEW_HEADERS]}
        ).execute()
    
    return sheet

# --- [4. Module: Leading Stock Scanner] ---
def get_leading_stocks_dynamic():
    # 시총 1,000억 이상의 전 종목 리스트 확보
    df_kospi = fdr.StockListing('KOSPI')
    df_kosdaq = fdr.StockListing('KOSDAQ')
    all_stocks = pd.concat([df_kospi, df_kosdaq])
    all_stocks = all_stocks[all_stocks['Marcap'] >= 100000000000]
    
    # 회전율 계산 및 상위 30개 추출
    all_stocks['Turnover_Rate'] = all_stocks['Amount'] / all_stocks['Marcap']
    candidates = all_stocks.sort_values(by='Turnover_Rate', ascending=False).head(30)
    candidate_list = [f"{row['Name']}({row['Code']})" for _, row in candidates.iterrows()]

    # Gemini 지능형 필터링 (섹터 쿼터제 포함)
    prompt = f"""
    아래 30개 종목 중 현재 시장의 핵심 테마(반도체, AI, 바이오 등)에 속하는 주도주 5개를 골라주세요.
    단, 동일 섹터가 3개를 넘지 않게 분산하세요.
    반환 형식: 종목명,종목코드,섹터명 (줄바꿈으로 구분, 다른 설명 금지)
    리스트: {', '.join(candidate_list)}
    """
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        if not response or not response.text: return []
        lines = response.text.strip().split('\n')
        return [tuple(map(str.strip, line.split(','))) for line in lines if len(line.split(',')) == 3][:5]
    except:
        return []

# --- [5. Module: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if len(df) < 20: return None
        df = df.tail(20)
        
        high_price = df['High'].max()
        # ATR 연산 (14일 변동성 폭)
        tr = pd.concat([df['High'] - df['Low'], 
                        abs(df['High'] - df['Close'].shift(1)), 
                        abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # 5일 VWAP 근사치
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        vwap_5d = vwap_5d.iloc[-1]
        
        # 타점 결정: MAX(5일 VWAP, 고점 - 1.5 ATR)
        entry_target = max(vwap_5d, high_price - (1.5 * atr))
        return round(entry_target), round(entry_target * 0.90)
    except:
        return None

# --- [6. Module: Telegram with Retry] ---
def send_telegram_with_retry(token, chat_id, text):
    for attempt in range(3):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                                 data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
            resp.raise_for_status()
            return True
        except:
            time.sleep(2 ** attempt)
    raise RuntimeError("Telegram 최종 전송 실패")

# --- [7. Main Workflow] ---
def main():
    try:
        # 인프라 초기화
        sheet_service = init_google_sheets()
        
        # 주도주 동적 스캐닝
        stocks = get_leading_stocks_dynamic()
        if not stocks:
            print("주도주 선별 실패")
            return

        trading_data = []
        telegram_msg = "🚨 <b>[에이전트 MTS 지시서]</b>\n\n"
        
        for name, code, theme in stocks:
            res = calculate_trading_signals(code)
            if not res: continue
            entry, stop = res
            name_esc = html.escape(name)
            
            # 데이터 수집
            trading_data.append([datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, "SCM 회전율/AI 분석", "대기", "N/A"])
            telegram_msg += f"🎯 <b>{name_esc}</b>\n- 섹터: {theme}\n- 타점: {entry:,}원\n- 손절: {stop:,}원\n\n"

        # 결과 적재 및 전송
        if trading_data:
            sheet_service.values().append(
                spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": trading_data}
            ).execute()
            send_telegram_with_retry(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg)
            print("성공: 데이터 기록 및 알림 전송 완료")
            
    except Exception as e:
        print(f"시스템 중단 에러: {e}")

if __name__ == "__main__":
    main()
