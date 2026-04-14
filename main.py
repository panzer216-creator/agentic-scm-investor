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

# --- [2. Global Initialization] ---
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [3. Module: Google Sheets Logic (Minimal for Diagnosis)] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

# --- [4. Module: Scanner with Heavy Logging] ---
def diagnose_market_scanner():
    diag_logs = []
    try:
        df_kospi = fdr.StockListing('KOSPI')
        df_kosdaq = fdr.StockListing('KOSDAQ')
        all_stocks = pd.concat([df_kospi, df_kosdaq])
        
        diag_logs.append(f"1. 조달: 시장 전체 {len(all_stocks)}개")
        
        # 시총 1000억 이상 필터
        filtered_stocks = all_stocks[all_stocks['Marcap'] >= 100000000000].copy()
        diag_logs.append(f"2. 필터: 시총 1천억 이상 {len(filtered_stocks)}개")
        
        filtered_stocks['Turnover_Rate'] = filtered_stocks['Amount'] / filtered_stocks['Marcap']
        top_30 = filtered_stocks.sort_values(by='Turnover_Rate', ascending=False).head(30)
        candidate_list = [f"{row['Name']}({row['Code']})" for _, row in top_30.iterrows()]
        
        prompt = f"전문 트레이더로서 다음 30개 중 주도주 15개를 '종목명,코드,섹터' 형식으로 골라줘: {', '.join(candidate_list)}"
        response = GEMINI_MODEL.generate_content(prompt)
        raw_ai_text = response.text if response else "AI_EMPTY"
        
        parsed_stocks = []
        if response and response.text:
            lines = response.text.strip().split('\n')
            for line in lines:
                clean = re.sub(r'^[0-9.\-\s*]+', '', line)
                parts = clean.split(',')
                if len(parts) >= 2:
                    parsed_stocks.append((parts[0].strip(), re.sub(r'[^0-9]', '', parts[1]), parts[-1].strip()))
        
        diag_logs.append(f"3. AI 선별: {len(parsed_stocks)}개 파싱 성공")
        return parsed_stocks, diag_logs, raw_ai_text
    except Exception as e:
        return [], [f"❌ 스캐닝 에러: {str(e)}"], "ERROR"

# --- [5. Module: Pricing with Numerical Audit] ---
def diagnose_pricing(name, symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = fdr.DataReader(symbol, start_date)
        if df is None or df.empty: return f"❌ {name}({symbol}): 데이터 로드 0행"
        
        row_count = len(df)
        df = df.tail(20)
        
        # 수치 연산 검증
        high_price = df['High'].max()
        tr = pd.concat([df['High'] - df['Low'], abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        vwap_val = vwap_5d.iloc[-1]
        
        if pd.isna(vwap_val) or pd.isna(atr):
            return f"❌ {name}({symbol}): 수치 NaN 발생 (Data={row_count}d)"
            
        entry = max(vwap_val, high_price - (1.5 * atr))
        return f"✅ {name}({symbol}): {row_count}d 로드 | VWAP:{round(vwap_val)} | ATR:{round(atr)} | 타점:{round(entry)}"
    except Exception as e:
        return f"❌ {name}({symbol}): 에러 {str(e)[:15]}"

# --- [6. Main Workflow: Diagnostic Mode] ---
def main():
    token = os.environ['TELEGRAM_BOT_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
    
    try:
        # 1. 시트 연동 테스트
        init_google_sheets()
        
        # 2. 마켓 스캐닝 진단
        stocks, scan_logs, raw_ai = diagnose_market_scanner()
        
        # 3. 개별 종목 수치 진단
        pricing_results = []
        for name, code, theme in stocks:
            res = diagnose_pricing(name, code)
            pricing_results.append(res)
            
        # 4. 종합 보고서 작성
        report = "🧪 <b>[V1.7 공정 정밀 진단서]</b>\n\n"
        report += "<b>[1. 인프라 단계]</b>\n" + "\n".join(scan_logs) + "\n\n"
        
        report += "<b>[2. AI 응답 원본]</b>\n"
        report += f"<code>{raw_ai[:150]}</code>\n\n"
        
        report += "<b>[3. 종목별 수치 전수조사]</b>\n"
        report += "\n".join(pricing_results) if pricing_results else "파싱된 종목 없음"
        
        # 텔레그램 발송
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": report, "parse_mode": "HTML"})
            
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": f"❌ 진단 중단: {e}"})

if __name__ == "__main__":
    main()
