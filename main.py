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

# [전략 비축 리스트] 시장 전체 리스트 API 오류 시 사용하는 핵심 주도주 50개
WATCHLIST = [
    "삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차", "기아", "셀트리온", "KB금융", "POSCO홀딩스", "NAVER", 
    "에코프로비엠", "에코프로", "HLB", "알테오젠", "엔켐", "리노공업", "레인보우로보틱스", "HPSP", "신성델타테크", "제주반도체",
    "한미반도체", "이수페타시스", "가온칩스", "두산에너빌리티", "포스코퓨처엠", "삼성SDI", "LG화학", "카카오", "SK이노베이션", "한화에어로스페이스",
    "현대로템", "LIG넥스원", "에이직랜드", "오픈엣지테크놀로지", "퀄리타스반도체", "테크윙", "자람테크놀로지", "폴라리스AI", "솔브레인", "동진쎄미켐",
    "유한양행", "한미약품", "리가켐바이오", "삼양식품", "대상", "아모레퍼시픽", "브이티", "실리콘투", "에이피알", "코스메카코리아"
]

# --- [2. Global Initialization] ---
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
GEMINI_MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- [3. Module: Google Sheets Logic] ---
def init_google_sheets():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

# --- [4. Module: AI Leading Stock Selection] ---
def get_leading_stocks_ai():
    prompt = f"""
    당신은 전문 트레이더입니다. 아래 리스트는 현재 한국 시장의 주요 테마주들입니다.
    이 중에서 오늘 시장의 분위기를 주도할 것으로 보이는 종목 10개를 선정하세요.
    반환 형식: 종목명 (설명 없이 한 줄에 하나씩만)
    리스트: {', '.join(WATCHLIST)}
    """
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        if not response or not response.text: return []
        # 줄바꿈으로 분리 후 빈 줄 제거
        names = [name.strip() for name in response.text.strip().split('\n') if name.strip()]
        return names[:10]
    except Exception as e:
        print(f"AI 선별 에러: {e}")
        return []

# --- [5. Module: Pricing Logic with Safety Buffer] ---
def calculate_signals(name):
    # 네이버 서버 부하 방지를 위한 지연 (SCM 속도 제어)
    time.sleep(0.5)
    
    start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        # FinanceDataReader는 기본적으로 네이버 소스를 사용함
        df = fdr.DataReader(name, start_date)
        if df is None or len(df) < 15: return None
        
        df = df.tail(20)
        high_price = df['High'].max()
        
        # 5일 VWAP 근사치 및 14일 ATR 계산
        vwap_5d = (df['Close'] * df['Volume']).rolling(5).sum() / df['Volume'].rolling(5).sum()
        tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift(1)), abs(df['Low']-df['Close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        entry_target = max(vwap_5d.iloc[-1], high_price - (1.5 * atr))
        return round(entry_target), round(entry_target * 0.90)
    except Exception as e:
        print(f"⚠️ {name} 연산 실패: {e}")
        return None

# --- [6. Module: Telegram Service] ---
def send_telegram(token, chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=15)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

# --- [7. Main Workflow] ---
def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    try:
        # 1. 시트 초기화
        sheet_service = init_google_sheets()
        
        # 2. AI 주도주 10선 추출 (쿼터 절약형)
        selected_names = get_leading_stocks_ai()
        if not selected_names:
            send_telegram(token, chat_id, "⚠️ AI 선별 공정 실패 (원재료 부족)")
            return

        trading_data = []
        telegram_msg = "🚨 <b>[V1.8 실전 MTS 지시서]</b>\n"
        telegram_msg += f"<i>(전략 비축 50선 중 AI 엄선 10개 분석)</i>\n\n"
        
        # 3. 개별 종목 정밀 가공
        for name in selected_names:
            res = calculate_signals(name)
            if not res: continue
            
            entry, stop = res
            name_esc = html.escape(name)
            
            # 구글 시트용 데이터 축적
            trading_data.append([
                datetime.now().strftime("%Y-%m-%d"), 
                "주도주(AI)", 
                name, 
                entry, 
                stop, 
                "전략 리스트 기반 분석", 
                "대기", 
                "N/A"
            ])
            
            # 텔레그램 지시서 본문 구성
            telegram_msg += f"🎯 <b>{name_esc}</b>\n- 타점: {entry:,}원 | 손절: {stop:,}원\n\n"

        # 4. 최종 결과물 출하
        if trading_data:
            sheet_service.values().append(
                spreadsheetId=SHEET_ID, 
                range=f"'{TARGET_TAB}'!A2", 
                valueInputOption="RAW", 
                insertDataOption="INSERT_ROWS", 
                body={"values": trading_data}
            ).execute()
            
            send_telegram(token, chat_id, telegram_msg)
            print("공정 완료: 시트 기록 및 텔레그램 발송 성공")
        else:
            send_telegram(token, chat_id, "⚠️ 분석 결과, 기술적 타점에 부합하는 종목이 없습니다.")
            
    except Exception as e:
        print(f"시스템 중단: {e}")
        send_telegram(token, chat_id, f"❌ 시스템 중단 에러: {e}")

if __name__ == "__main__":
    main()
