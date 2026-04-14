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
# Gemini API 전역 초기화 (반복 호출에 따른 리소스 낭비 방지)
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [Module D: Google Sheets Logic] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="Trading_Log!A1:H1").execute()
    current_header = result.get('values', [[]])[0]
    
    if current_header != NEW_HEADERS:
        sheet.values().clear(spreadsheetId=SHEET_ID, range="Trading_Log!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID, range="Trading_Log!A1",
            valueInputOption="RAW", body={"values": [NEW_HEADERS]}
        ).execute()
        print("Sheet initialized and headers created.")
    
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
        if not response.text:
            raise ValueError("Gemini 응답이 비어있습니다.")
        return response.text
    except Exception as e:
        print(f"Gemini API 호출 실패: {e}")
        return None

# --- [Module C: Dynamic Pricing Logic] ---
def calculate_trading_signals(symbol):
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    df = fdr.DataReader(symbol, start_date)
    
    # 20일치 데이터가 안 되면 연산 불가 판정
    if len(df) < 20: 
        return None
    
    df = df.tail(20)
    
    high_price = df['High'].max()
    
    # 미사용 변수(curr_price) 삭제, 메모리 확보
    tr = pd.concat([df['High'] - df['Low'], 
                    abs(df['High'] - df['Close'].shift(1)), 
                    abs(df['Low'] - df['Close'].shift(1))], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
    vwap_5d = vwap_5d.iloc[-1]
    
    entry_target = max(vwap_5d, high_price - (1.5 * atr))
    stop_loss = entry_target * 0.90
    
    return round(entry_target), round(stop_loss)

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
                print(f"Telegram 전송 실패 (시도 {attempt+1}/{max_retries}), {wait}초 대기: {e}")
                time.sleep(wait)
    
    # 루프 종료 후에도 실패면 에러 발생시켜 상위 프로세스에 알림
    raise RuntimeError("Telegram 최종 전송 실패")

# --- [Main Execution Flow] ---
def main():
    sheet_service = init_google_sheets()
    
    # (실제 환경에서는 fdr을 통해 동적으로 ETF 리스트를 수집하는 로직이 들어감)
    sample_etf_list = "KODEX 200, TIGER 반도체, KODEX 인버스, KODEX 로봇"
    
    filtered_etfs = filter_etfs_with_gemini(sample_etf_list)
    
    # API 장애 등으로 필터링 실패 시 크래시 방지 및 우아한 종료
    if filtered_etfs is None:
        print("ETF 필터링 실패 — 오늘 분석 중단")
        return

    sample_stocks = [("삼성전기", "009150", "반도체/부품"), ("에이스테크", "088800", "5G/통신")]
    
    trading_data = []
    telegram_msg = "🚨 <b>[에이전트 MTS 지시서]</b>\n\n"
    
    for name, code, theme in sample_stocks:
        result = calculate_trading_signals(code)
        
        if result is None:
            print(f"{name} 데이터 부족으로 연산 스킵")
            continue
            
        entry, stop = result
        
        # HTML 파싱 에러 방지를 위해 변환된 이름 사용
        name_escaped = html.escape(name)
        reasoning = f"{theme} 섹터 자본 유입 확인 및 회전율 상위 랭크."
        
        row = [datetime.now().strftime("%Y-%m-%d"), theme, f"{name}({code})", entry, stop, reasoning, "대기", "N/A"]
        trading_data.append(row)
        
        # 메시지 템플릿에 안전한 변수(name_escaped) 매핑
        telegram_msg += f"🎯 <b>{name_escaped}</b>\n- 타점: {entry:,}원\n- 손절: {stop:,}원\n\n"

    # 추출된 종목이 1개라도 있을 때만 저장 및 알림 발송 (현금 100% 로직 반영)
    if trading_data:
        sheet_service.values().append(
            spreadsheetId=SHEET_ID, range="Trading_Log!A2",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": trading_data}
        ).execute()
        
        send_telegram_with_retry(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], telegram_msg)
    else:
        print("오늘 조건에 맞는 주도주가 없어 포트폴리오를 비워둡니다 (현금 보유 관망).")

if __name__ == "__main__":
    main()
