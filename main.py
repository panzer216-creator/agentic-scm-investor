import os
import json
import time
import html
import re
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
    
    spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_names = [s['properties']['title'] for s in sheets]
    
    if TARGET_TAB not in sheet_names:
        first_sheet_id = sheets[0]['properties']['sheetId']
        batch_update_request = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': first_sheet_id, 'title': TARGET_TAB}, 'fields': 'title'}}]}
        sheet.batchUpdate(spreadsheetId=SHEET_ID, body=batch_update_request).execute()
        time.sleep(1)
    
    range_name = f"'{TARGET_TAB}'!A1:H1"
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=range_name).execute()
    current_header = result.get('values', [[]])[0]
    
    if current_header != NEW_HEADERS:
        sheet.values().clear(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A:Z").execute()
        sheet.values().update(spreadsheetId=SHEET_ID, range=range_name, valueInputOption="RAW", body={"values": [NEW_HEADERS]}).execute()
    return sheet

# --- [4. Module: Leading Stock Scanner] ---
def get_leading_stocks_dynamic():
    try:
        # 시장 데이터 로드
        df_kospi = fdr.StockListing('KOSPI')
        df_kosdaq = fdr.StockListing('KOSDAQ')
        all_stocks = pd.concat([df_kospi, df_kosdaq])
        
        # 1차 필터링: 시총 1000억 이상 (유동성 확보)
        base_count = len(all_stocks)
        all_stocks = all_stocks[all_stocks['Marcap'] >= 100000000000]
        filtered_count = len(all_stocks)
        
        print(f"전체 {base_count}개 중 시총 기준 {filtered_count}개 통과")
        
        # 회전율 계산
        all_stocks['Turnover_Rate'] = all_stocks['Amount'] / all_stocks['Marcap']
        top_candidates = all_stocks.sort_values(by='Turnover_Rate', ascending=False).head(30)
        candidate_list = [f"{row['Name']}({row['Code']})" for _, row in top_candidates.iterrows()]

        prompt = f"""
        당신은 주식 시장 주도주를 발굴하는 전문가입니다. 
        다음 30개 후보 중 현재 시장 테마에 부합하는 주도주 15개를 엄선하세요.
        반환 형식: 종목명,종목코드,섹터 (설명 없이 한 줄에 하나씩만)
        리스트: {', '.join(candidate_list)}
        """
        response = GEMINI_MODEL.generate_content(prompt)
        final_selection = []
        
        if response and response.text:
            lines = response.text.strip().split('\n')
            for line in lines:
                clean_line = re.sub(r'^[0-9.\-\s*]+', '', line)
                parts = clean_line.split(',')
                if len(parts) >= 3:
                    final_selection.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
        
        # 백업: AI가 한 개도 못 골랐을 경우 기계적으로 상위 10개 투입
        if not final_selection:
            for _, row in top_candidates.head(10).iterrows():
                final_selection.append((row['Name'], row['Code'], "회전율상위(기계적)"))
        
        return final_selection, filtered_count
    except Exception as e:
        print(f"스캐닝 치명적 오류: {e}")
        return [], 0

# --- [5. Module: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if df is None or df.empty: return "EMPTY_DATA"
        if len(df) < 15: return f"LACK_DATA({len(df)}일)"
        
        df = df.tail(20)
        high_price = df['High'].max()
        tr = pd.concat([df['High'] - df['Low'], abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        vwap_val = vwap_5d.iloc[-1]
        
        if pd.isna(vwap_val) or pd.isna(atr): return "CALC_ERROR(NaN)"
        
        entry = max(vwap_val, high_price - (1.5 * atr))
        return round(entry), round(entry * 0.90)
    except Exception as e:
        return f"ERR:{str(e)[:15]}"

# --- [6. Module: Telegram Service] ---
def send_telegram(token, chat_id, text):
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                  data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)

# --- [7. Main Workflow] ---
def main():
    try:
        sheet_service = init_google_sheets()
        stocks, market_count = get_leading_stocks_dynamic()
        
        trading_data = []
        audit_log = [] # 전수 조사 로그
        telegram_msg = f"🚨 <b>[에이전트 MTS 지시서 V1.5]</b>\n"
        telegram_msg += f"📦 시장 모수: {market_count}개 ➡️ 검토: {len(stocks)}개\n\n"
        
        success_count = 0
        for name, code, theme in stocks:
            res = calculate_trading_signals(code)
            
            if isinstance(res, tuple):
                success_count += 1
                if success_count <= 5: # 최종 5개만 상세 보고
                    entry, stop = res
                    name_esc = html.escape(name)
                    trading_data.append([datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, "SCM/AI 감사 시스템", "대기", "N/A"])
                    telegram_msg += f"🎯 <b>{name_esc}</b>\n- 타점: {entry:,}원 | 손절: {stop:,}원\n\n"
                audit_log.append(f"✅ {name}: 통과")
            else:
                audit_log.append(f"❌ {name}: {res}")

        # 감사 보고서 하단 추가
        audit_summary = "\n🔍 <b>[전수 조사 사유서]</b>\n" + "\n".join(audit_log)

        if trading_data:
            sheet_service.values().append(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}).execute()
            send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg + audit_summary)
        else:
            fail_report = f"⚠️ <b>[공정 중단 보고]</b>\n검토한 {len(stocks)}개 종목이 모두 필터에서 탈락했습니다.\n"
            send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], fail_report + audit_summary)
            
    except Exception as e:
        send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], f"❌ 시스템 치명적 결함: {e}")

if __name__ == "__main__":
    main()
