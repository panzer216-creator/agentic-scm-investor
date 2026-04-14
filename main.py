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
        df_kospi = fdr.StockListing('KOSPI')
        df_kosdaq = fdr.StockListing('KOSDAQ')
        all_stocks = pd.concat([df_kospi, df_kosdaq])
        all_stocks = all_stocks[all_stocks['Marcap'] >= 100000000000] # 기준 소폭 완화
        
        all_stocks['Turnover_Rate'] = all_stocks['Amount'] / all_stocks['Marcap']
        top_candidates = all_stocks.sort_values(by='Turnover_Rate', ascending=False).head(30)
        candidate_list = [f"{row['Name']}({row['Code']})" for _, row in top_candidates.iterrows()]

        prompt = f"""
        전문 트레이더로서 다음 30개 중 주도주 15개를 선정하세요.
        반환: 종목명,종목코드,섹터 (설명 없이 한 줄에 하나씩)
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
        
        if not final_selection:
            for _, row in top_candidates.head(15).iterrows():
                final_selection.append((row['Name'], row['Code'], "회전율상위"))
        
        return final_selection
    except Exception as e:
        print(f"스캐닝 오류: {e}")
        return []

# --- [5. Module: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    # 60일치 넉넉하게 로드
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if len(df) < 15: return "DATA_LACK" # 데이터 부족 사유 반환
        
        df = df.tail(20)
        high_price = df['High'].max()
        tr = pd.concat([df['High'] - df['Low'], abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        
        entry = max(vwap_5d.iloc[-1], high_price - (1.5 * atr))
        return round(entry), round(entry * 0.90)
    except Exception as e:
        return f"ERROR:{str(e)[:20]}"

# --- [6. Module: Telegram Service] ---
def send_telegram(token, chat_id, text):
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                  data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)

# --- [7. Main Workflow] ---
def main():
    try:
        sheet_service = init_google_sheets()
        stocks = get_leading_stocks_dynamic()
        
        trading_data = []
        process_log = [] # 공정 추적 로그
        telegram_msg = f"🚨 <b>[에이전트 MTS 지시서]</b>\n\n"
        
        success_count = 0
        for name, code, theme in stocks:
            res = calculate_trading_signals(code)
            
            if isinstance(res, tuple): # 성공
                success_count += 1
                if success_count > 5: continue
                entry, stop = res
                name_esc = html.escape(name)
                trading_data.append([datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, "SCM/AI 분석", "대기", "N/A"])
                telegram_msg += f"🎯 <b>{name_esc}</b>\n- 섹터: {theme}\n- 타점: {entry:,}원\n- 손절: {stop:,}원\n\n"
                process_log.append(f"✅ {name}: 통과")
            else: # 실패 사유 기록
                process_log.append(f"❌ {name}: {res}")

        if trading_data:
            sheet_service.values().append(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_data}).execute()
            # 하단에 추적 로그 추가
            telegram_msg += "------------------\n🔍 <b>공정 추적 로그</b>\n" + "\n".join(process_log[:15])
            send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg)
        else:
            fail_report = "⚠️ <b>[수율 0% 보고]</b>\n대상 종목은 찾았으나 기술적 필터에서 모두 탈락했습니다.\n\n"
            fail_report += "🔍 <b>검토 리스트:</b>\n" + "\n".join(process_log[:15])
            send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], fail_report)
            
    except Exception as e:
        send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], f"❌ 시스템 중단: {e}")

if __name__ == "__main__":
    main()
