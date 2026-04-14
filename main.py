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

# --- [Global Initialization] ---
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [Module D: Google Sheets Logic - 보완됨] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    # 1. 스프레드시트의 메타데이터를 가져와 시트(탭) 목록 확인
    spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_names = [s['properties']['title'] for s in sheets]
    
    # 2. 'Trading_Log' 탭이 없는 경우 처리
    if "Trading_Log" not in sheet_names:
        # 첫 번째 시트의 ID를 가져와 이름을 'Trading_Log'로 강제 변경 (창고 구역 설정)
        first_sheet_id = sheets[0]['properties']['sheetId']
        batch_update_request = {
            'requests': [{
                'updateSheetProperties': {
                    'properties': {'sheetId': first_sheet_id, 'title': 'Trading_Log'},
                    'fields': 'title'
                }
            }]
        }
        sheet.batchUpdate(spreadsheetId=SHEET_ID, body=batch_update_request).execute()
        print("기존 시트 이름을 'Trading_Log'로 변경했습니다.")
    
    # 3. 이제 안전하게 헤더 체크 및 초기화 진행
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="Trading_Log!A1:H1").execute()
    current_header = result.get('values', [[]])[0]
    
    if current_header != NEW_HEADERS:
        sheet.values().clear(spreadsheetId=SHEET_ID, range="Trading_Log!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID, range="Trading_Log!A1",
            valueInputOption="RAW", body={"values": [NEW_HEADERS]}
        ).execute()
        print("시트가 새로운 양식으로 초기화되었습니다.")
    
    return sheet

# --- [Module A: Gemini Intelligent Filter] ---
def filter_etfs_with_gemini(etf_names):
    prompt = f"""
    아래 ETF 리스트 중 코스피/코스닥 지수 추종(200, 150), 레버리지, 인버스, 고배당, 그룹주 테마를 모두 제외하세요. 
    오직 '특정 산업 또는 기술 테마'만 골라내어 콤마로 구분된 리스트로 반환하세요.
    다른 설명은 절대 하지 마세요.
    리스트: {etf_names}
    """
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        if not response or not response.text:
            raise ValueError("Gemini 응답이 비어있습니다.")
        return response.text
    except Exception as e:
        print(f"Gemini API 호출 실패: {e}")
        return None

# --- [Module C: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if len(df) < 20: return None
        df = df.tail(20)
        
        high_price = df['High'].max()
        tr = pd.concat([df['High'] - df['Low'], 
                        abs(df['High'] - df['Close'].shift(1)), 
                        abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        vwap_5d = vwap_5d.iloc[-1]
        
        entry_target = max(vwap_5d, high_price - (1.5 * atr))
        stop_loss = entry_target * 0.90
        
        return round(entry_target), round(stop_loss)
    except:
        return None

# --- [Module E: Telegram with Retry] ---
def send_telegram_with_retry(token, chat_id, text, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"재시도 {attempt+1}/{max_retries}: {e}")
                time.sleep(wait)
    raise RuntimeError("Telegram 최종 전송 실패")

# --- [Main Execution Flow] ---
def main():
    try:
        sheet_service = init_google_sheets()
        
        # 샘플 테마 스캔 (실전에서는 fdr 스캐너 작동)
        sample_etf_list = "TIGER 반도체, KODEX 200, KODEX 로봇, TIGER 2차전지"
        filtered_etfs = filter_etfs_with_gemini(sample_etf_list)
        
        if filtered_etfs is None:
            print("ETF 필터링 실패로 중단합니다.")
            return

        # 주도주 예시 (삼성전기, 에이스테크)
        sample_stocks = [("삼성전기", "009150", "반도체/부품"), ("에이스테크", "088800", "5G/통신")]
        
        trading_data = []
        telegram_msg = "🚨 <b>[에이전트 MTS 지시서]</b>\n\n"
        
        for name, code, theme in sample_stocks:
            result = calculate_trading_signals(code)
            if result is None: continue
                
            entry, stop = result
            name_escaped = html.escape(name)
            reasoning = f"{theme} 섹터 자본 유입 확인 및 회전율 상위 랭크."
            
            row = [datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, reasoning, "대기", "N/A"]
            trading_data.append(row)
            telegram_msg += f"🎯 <b>{name_escaped}</b>\n- 타점: {entry:,}원\n- 손절: {stop:,}원\n\n"

        if trading_data:
            sheet_service.values().append(
                spreadsheetId=SHEET_ID, range="Trading_Log!A2",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": trading_data}
            ).execute()
            send_telegram_with_retry(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg)
        else:
            print("조건에 맞는 종목이 없습니다.")
            
    except Exception as e:
        print(f"시스템 중단 에러: {e}")

if __name__ == "__main__":
    main()
