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
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0')
MASTER_TAB = "Seed_Data_414"
TARGET_TAB = "Trading_Log"
SYSTEM_STATE_TAB = "System_State"
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# [V3.2 신규] 섹터 키워드 매핑 사전 (정확한 매칭 보장)
CATEGORY_KEYWORD_MAP = {
    "반도체": "KODEX 반도체",
    "바이오": "KODEX 바이오",
    "뷰티": "KODEX K-뷰티",
    "로봇": "TIGER 로봇TOP10",
    "자동차": "TIGER 현대차그룹+",
    "전력": "KODEX AI전력핵심설비",
    "우주": "TIGER 우주방산",
    "방산": "TIGER 우주방산",
    "조선": "KODEX 조선",
    "2차전지": "TIGER 2차전지테마"
}

# --- [2 ~ 4. Service, State, Polling (동일)] ---
def get_service():
    try:
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        return build('sheets', 'v4', credentials=creds).spreadsheets()
    except Exception as e:
        print(f"[Error] 인증 실패: {e}")
        raise

def _read_state(service):
    try:
        result = service.values().get(spreadsheetId=SHEET_ID, range=f"'{SYSTEM_STATE_TAB}'!B1").execute()
        values = result.get('values', [])
        return int(values[0][0]) if values and values[0] else 0
    except: return 0

def _write_state(service, last_update_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = {"values": [["last_update_id", last_update_id], ["last_run_time", now_str]]}
    try:
        service.values().update(spreadsheetId=SHEET_ID, range=f"'{SYSTEM_STATE_TAB}'!A1:B2", valueInputOption="RAW", body=body).execute()
    except: pass

def get_telegram_logs(service):
    last_update_id = _read_state(service)
    offset = last_update_id + 1 if last_update_id > 0 else 0
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    
    try:
        res = requests.get(url, params={"offset": offset, "limit": 100, "timeout": 5}, timeout=10).json()
        if not res.get('ok'): return []
        updates = res.get('result', [])
        if not updates: return []
        
        logs, max_id = [], last_update_id
        for item in updates:
            u_id = item.get('update_id', 0)
            max_id = max(max_id, u_id)
            msg = item.get('message', {})
            text = msg.get('text', '')
            if '#기록' in text:
                logs.append({"raw": text, "clean": text.replace(" ", "").replace("\n", ""), "ts": msg.get('date', 0)})
        
        if max_id > last_update_id: _write_state(service, max_id)
        return logs
    except: return []

def send_telegram_chunked(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for idx, chunk in enumerate(chunks):
        for attempt in range(3):
            try:
                res = requests.post(url, data={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML"}, timeout=15)
                if res.status_code == 200: break
                elif res.status_code == 429: time.sleep(int(res.json().get('parameters', {}).get('retry_after', 5)))
                else: time.sleep(2 ** attempt) if attempt < 2 else None
            except: time.sleep(2 ** attempt) if attempt < 2 else None
        if idx < len(chunks) - 1: time.sleep(0.5)

# --- [5. Core Analysis Logic] ---
def analyze_etf_trend(ticker: str) -> str:
    time.sleep(1)
    try:
        start_date = (datetime.today() - timedelta(days=45)).strftime('%Y-%m-%d') # 영업일 확보를 위해 45일로 연장
        df = fdr.DataReader(ticker, start_date)
        if df is None or len(df) < 10: return "상태 불명"
        current = int(df['Close'].iloc[-1])
        ma10 = df['Close'].rolling(10).mean().iloc[-1]
        return "🟢상승장" if current > ma10 else "🔴하락장"
    except: return "상태 불명"

def analyze_stock(cat: str, name: str, ticker: str, sector_status: str) -> dict | None:
    time.sleep(1)
    try:
        start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker, start_date)
        if df is None or len(df) < 20: return None
        
        current = int(df['Close'].iloc[-1])
        df_tail = df.tail(20)
        
        tr = pd.concat([
            df_tail['High'] - df_tail['Low'],
            abs(df_tail['High'] - df_tail['Close'].shift(1)),
            abs(df_tail['Low'] - df_tail['Close'].shift(1))
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        vwap = (df_tail['Close'] * df_tail['Volume']).rolling(5).sum() / df_tail['Volume'].rolling(5).sum()
        entry = round(max(vwap.iloc[-1], df_tail['High'].max() - (1.5 * atr)))
        stop = round(entry * 0.90)
        gap_pct = round(((current - entry) / entry) * 100, 2) # 양수면 타점 위, 음수면 타점 아래
        
        # 직관적인 용어로 변경
        is_overshooting = current > (entry + 2.0 * atr)
        if is_overshooting: action, reason = "과열", "단기 급등 (2ATR 초과)"
        elif sector_status == "🔴하락장": action, reason = "매수대기", "섹터 하락으로 매수 보류"
        elif sector_status == "상태 불명": action, reason = "매수대기", "섹터 추세 데이터 누락"
        elif current >= entry: action, reason = "매수", "섹터 상승 및 개별 타점 돌파"
        else: action, reason = "매수대기", f"타점까지 {gap_pct}% 남음"
            
        return {"cat": cat, "name": name, "current": current, "entry": entry, "stop": stop, "gap_pct": gap_pct, "action": action, "reason": reason}
    except: return None

# --- [6. Main Workflow] ---
def main():
    service = get_service()
    master_list = service.values().get(spreadsheetId=SHEET_ID, range=f"'{MASTER_TAB}'!A2:C").execute().get('values', [])
    user_logs = get_telegram_logs(service)
    
    sector_env = {}
    report_etf, report_wait = [], []
    buy_candidates = [] # 매수 종목 정렬을 위한 리스트
    trading_rows = []

    # 1. 섹터 분석
    for row in master_list:
        if len(row) < 3 or row[0] != "전략 ETF": continue
        status = analyze_etf_trend(row[2])
        sector_env[row[1]] = status
        report_etf.append(f"• {html.escape(row[1])} : {status}")

    # 2. 개별 종목 분석
    for row in master_list:
        if len(row) < 3 or row[0] == "전략 ETF": continue
        cat, name, ticker = row[0], row[1], row[2]
        
        # [V3.2 개선] 키워드 기반 확실한 섹터 매칭
        sector_status = "상태 불명"
        for kw, etf_name in CATEGORY_KEYWORD_MAP.items():
            if kw in cat:
                sector_status = sector_env.get(etf_name, "상태 불명")
                break
                
        res = analyze_stock(cat, name, ticker, sector_status)
        if not res: continue

        comment = next((log['raw'] for log in user_logs if name.replace(" ", "") in log['clean']), "")
        trading_rows.append([datetime.now().strftime("%Y-%m-%d"), cat, name, res['current'], res['entry'], res['stop'], res['action'], res['reason'], comment])

        if res['action'] == "매수":
            buy_candidates.append(res)
        else:
            icon = "⚠️" if res['action'] == "과열" else "⏳"
            report_wait.append(f"• {icon} <b>[{html.escape(cat)}] {html.escape(name)}</b>\n  - 현재가: {res['current']:,}원 | 타점: {res['entry']:,}원\n  - 사유: {html.escape(res['reason'])}")

    # 3. 매수 종목 매력도 정렬 (이격도 오름차순)
    report_buy = []
    buy_candidates = sorted(buy_candidates, key=lambda x: x['gap_pct'])
    for i, item in enumerate(buy_candidates):
        rank_icon = "🔥최우선" if i == 0 else "✅일반"
        report_buy.append(f"• <b>[{rank_icon}] [{html.escape(item['cat'])}] {html.escape(item['name'])}</b>\n  - 현재가: {item['current']:,}원 | 타점: <b>{item['entry']:,}원</b> (+{item['gap_pct']}% 초과)\n  - 손절가: {item['stop']:,}원")

    # 4. 최종 보고서
    full_msg = f"🚨 <b>[V3.2 트레이딩 리포트]</b>\n\n📊 <b>[섹터 환경 (ETF)]</b>\n" + "\n".join(report_etf) + "\n\n"
    full_msg += f"🚀 <b>[매수 대상]</b>\n" + ("\n".join(report_buy) if report_buy else "• 조건 충족 종목 없음") + "\n\n"
    full_msg += f"⏳ <b>[매수대기 및 과열]</b>\n" + ("\n".join(report_wait) if report_wait else "• 해당 없음")
    
    send_telegram_chunked(full_msg)
    
    if trading_rows:
        service.values().append(spreadsheetId=SHEET_ID, range=f"'{TARGET_TAB}'!A2", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": trading_rows}).execute()
    print("[Success] V3.2 완료")

if __name__ == "__main__":
    main()
