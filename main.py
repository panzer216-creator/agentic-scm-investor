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

# ─────────────────────────────────────────
# [1. Configuration]
# ─────────────────────────────────────────
SHEET_ID          = os.environ.get('GOOGLE_SHEET_ID', '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0')
MASTER_TAB        = "Seed_Data_414"
TARGET_TAB        = "Trading_Log"
SYSTEM_STATE_TAB  = "System_State"
TELEGRAM_TOKEN    = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID           = os.environ.get('TELEGRAM_CHAT_ID')


# ─────────────────────────────────────────
# [2. Google Sheets API Service]
# ─────────────────────────────────────────
def get_service():
    try:
        creds_dict = json.loads(os.environ.get('GOOGLE_SHEETS_CREDENTIALS'))
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=creds).spreadsheets()
    except Exception as e:
        print(f"[Error] 서비스 계정 인증 실패: {e}")
        raise


# ─────────────────────────────────────────
# [3. System State Management]
# ─────────────────────────────────────────
def init_system_state(service):
    """
    System_State 탭 존재 여부 확인 및 초기값 세팅.
    탭이 없으면 자동 생성 시도 → 실패 시 명확한 에러 메시지 출력.
    """
    try:
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range=f"'{SYSTEM_STATE_TAB}'!A1:B2"
        ).execute()
        # 탭은 있지만 초기값이 없는 경우
        if not result.get('values'):
            _write_state(service, 0)
            print("[System] System_State 초기값 설정 완료")
        else:
            print(f"[System] System_State 로드 완료 (last_update_id={result['values'][0][1]})")

    except Exception as e:
        # 탭 자체가 없는 경우 → 자동 생성 시도
        print(f"[System] '{SYSTEM_STATE_TAB}' 탭 접근 실패: {e}")
        try:
            service.batchUpdate(
                spreadsheetId=SHEET_ID,
                body={'requests': [{'addSheet': {'properties': {'title': SYSTEM_STATE_TAB}}}]}
            ).execute()
            _write_state(service, 0)
            print(f"[System] '{SYSTEM_STATE_TAB}' 탭 자동 생성 완료")
        except Exception as e2:
            # 자동 생성도 실패 → 로그만 남기고 계속 진행 (offset=0 으로 폴링)
            print(f"[System] 탭 자동 생성 실패: {e2} — offset=0으로 계속 진행합니다.")


def _read_state(service):
    try:
        result = service.values().get(
            spreadsheetId=SHEET_ID,
            range=f"'{SYSTEM_STATE_TAB}'!B1"
        ).execute()
        values = result.get('values', [])
        return int(values[0][0]) if values and values[0] else 0
    except Exception as e:
        print(f"[State] 체크포인트 읽기 실패 (offset=0으로 진행): {e}")
        return 0


def _write_state(service, last_update_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = {
        "values": [
            ["last_update_id", last_update_id],
            ["last_run_time",  now_str]
        ]
    }
    try:
        service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"'{SYSTEM_STATE_TAB}'!A1:B2",
            valueInputOption="RAW",
            body=body
        ).execute()
        print(f"[State] 저장 완료: last_update_id={last_update_id}, time={now_str}")
    except Exception as e:
        print(f"[State] 체크포인트 기록 실패: {e}")


# ─────────────────────────────────────────
# [4. Telegram Polling]
# ─────────────────────────────────────────
def get_telegram_logs(service):
    """
    offset 기반 Telegram #기록 메시지 수거.
    처리 완료된 max update_id를 Sheets에 영속화.
    """
    last_update_id = _read_state(service)
    offset = last_update_id + 1 if last_update_id > 0 else 0
    print(f"[Polling] getUpdates 시작 (offset={offset})")

    url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": offset, "limit": 100, "timeout": 5}

    try:
        res = requests.get(url, params=params, timeout=10).json()
        if not res.get('ok'):
            print(f"[Polling] API 오류: {res.get('description')}")
            return []

        updates = res.get('result', [])
        if not updates:
            print("[Polling] 신규 메시지 없음")
            return []

        logs   = []
        max_id = last_update_id

        for item in updates:
            u_id   = item.get('update_id', 0)
            max_id = max(max_id, u_id)
            msg    = item.get('message', {})
            text   = msg.get('text', '')

            if '#기록' in text:
                logs.append({
                    "raw":   text,
                    "clean": text.replace(" ", "").replace("\n", ""),
                    "ts":    msg.get('date', 0)
                })
                print(f"[Polling] #기록 수집: {text[:60]}")

        if max_id > last_update_id:
            _write_state(service, max_id)

        print(f"[Polling] 완료: 전체 {len(updates)}건 / #기록 {len(logs)}건")
        return logs

    except requests.exceptions.Timeout:
        print("[Polling] Telegram 응답 timeout — 빈 목록으로 진행")
        return []
    except Exception as e:
        print(f"[Polling] 예외: {type(e).__name__}: {e}")
        return []


# ─────────────────────────────────────────
# [5. Telegram Messaging — Backoff + Chunking]
# ─────────────────────────────────────────
def send_telegram_with_retry(text: str):
    """
    4000자 단위 청크 분할 + 지수 백오프 재전송.

    수정 포인트 (v3.1 대비):
    - 비 429 실패 시에도 sleep 후 재시도
    - 마지막 attempt에서는 sleep 생략
    - bare except → Exception으로 교체, 로그 출력
    - 청크 성공/실패 여부 명확히 추적
    """
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LEN = 4000
    chunks  = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]

    for idx, chunk in enumerate(chunks):
        sent = False
        for attempt in range(3):
            try:
                res = requests.post(
                    url,
                    data={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML"},
                    timeout=15
                )
                if res.status_code == 200:
                    sent = True
                    break
                elif res.status_code == 429:
                    retry_after = int(res.json().get('parameters', {}).get('retry_after', 5))
                    print(f"[Telegram] Rate limit — {retry_after}초 대기 후 재시도")
                    time.sleep(retry_after)
                else:
                    # 그 외 HTTP 에러 (5xx 등)
                    if attempt < 2:
                        wait = 2 ** attempt
                        print(f"[Telegram] 청크 {idx+1} HTTP {res.status_code} — {wait}초 후 재시도")
                        time.sleep(wait)

            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    print(f"[Telegram] 예외 (시도 {attempt+1}/3): {type(e).__name__}: {e} — {wait}초 후 재시도")
                    time.sleep(wait)
                else:
                    print(f"[Telegram] 예외 (최종 실패): {type(e).__name__}: {e}")

        if not sent:
            print(f"[Telegram] 청크 {idx+1}/{len(chunks)} 최종 전송 실패")

        # 청크 간 최소 간격 (마지막 청크 제외)
        if idx < len(chunks) - 1:
            time.sleep(0.5)


# ─────────────────────────────────────────
# [6. Core Analysis Logic]
# ─────────────────────────────────────────
def analyze_etf_trend(ticker: str) -> str:
    """ETF 10일 이동평균선 기반 섹터 환경 판별"""
    time.sleep(1)
    try:
        start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker, start_date)
        if df is None or df.empty:
            return "상태 불명"
        if len(df) < 10:
            print(f"[ETF] {ticker} 데이터 부족 ({len(df)}일) — 10일 MA 계산 불가")
            return "상태 불명"
        current = int(df['Close'].iloc[-1])
        ma10    = df['Close'].rolling(10).mean().iloc[-1]
        return "🟢상승" if current > ma10 else "🔴하락"
    except Exception as e:
        print(f"[ETF] {ticker} 분석 실패: {type(e).__name__}: {e}")
        return "상태 불명"


def analyze_stock(name: str, ticker: str, sector_status: str) -> dict | None:
    """
    개별 종목 VWAP/ATR 타점 연산 및 섹터 연계 판정.

    수정 포인트 (v3.1 대비):
    - len(df) < 20 최소 데이터 가드 추가 (Regression 수정)
    - ATR 3요소 유지
    """
    time.sleep(1)
    try:
        start_date = (datetime.today() - timedelta(days=60)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker, start_date)

        if df is None or df.empty:
            return None
        # rolling(14) 연산을 위한 최소 데이터 보장
        if len(df) < 20:
            print(f"[Stock] {name} 데이터 부족 ({len(df)}일) — 스킵")
            return None

        current = int(df['Close'].iloc[-1])
        df_tail = df.tail(20)

        # ATR 3요소 완전체 (Wilder's True Range)
        tr = pd.concat([
            df_tail['High'] - df_tail['Low'],
            abs(df_tail['High'] - df_tail['Close'].shift(1)),
            abs(df_tail['Low']  - df_tail['Close'].shift(1))
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # VWAP (5일 가중 평균 단가)
        vwap = (
            (df_tail['Close'] * df_tail['Volume']).rolling(5).sum() /
            df_tail['Volume'].rolling(5).sum()
        )
        entry   = round(max(vwap.iloc[-1], df_tail['High'].max() - (1.5 * atr)))
        stop    = round(entry * 0.90)
        gap_pct = round(((entry - current) / current) * 100, 2)

        # 판정 로직 (우선순위 순)
        is_overshooting = current > (entry + 2.0 * atr)

        if is_overshooting:
            action, reason = "⚠️ 과열",    "2ATR 초과 단기 급등"
        elif sector_status == "🔴하락":
            action, reason = "⏳ 섹터관망", "타점 도달이나 섹터 하락장"
        elif sector_status == "상태 불명":
            action, reason = "⏳ 확인필요", "섹터 추세 데이터 확인 불가"
        elif current >= entry:
            action, reason = "🚀 매수",    "섹터 상승 및 개별 타점 돌파"
        else:
            action, reason = "⏳ 대기",    f"타점 대비 {gap_pct}% 이격"

        return {
            "name":    name,
            "current": current,
            "entry":   entry,
            "stop":    stop,
            "action":  action,
            "reason":  reason
        }
    except Exception as e:
        print(f"[Stock] {name}({ticker}) 분석 실패: {type(e).__name__}: {e}")
        return None


# ─────────────────────────────────────────
# [7. Main Workflow]
# ─────────────────────────────────────────
def main():
    service = get_service()
    init_system_state(service)

    # BOM(원자재) 로드
    master_list = service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{MASTER_TAB}'!A2:C"
    ).execute().get('values', [])

    user_logs = get_telegram_logs(service)

    sector_env                      = {}
    report_etf, report_buy, report_wait = [], [], []
    trading_rows                    = []

    # ── 1. 섹터 ETF 분석 ────────────────
    for row in master_list:
        if len(row) < 3:          # 빈 행 또는 불완전 행 방어
            continue
        if row[0] != "전략 ETF":
            continue
        status              = analyze_etf_trend(row[2])
        sector_env[row[1]]  = status
        report_etf.append(f"• {html.escape(row[1])} : {status}")

    # ── 2. 개별 종목 분석 ────────────────
    for row in master_list:
        if len(row) < 3:
            continue
        if row[0] == "전략 ETF":
            continue

        cat, name, ticker = row[0], row[1], row[2]

        # 섹터 매칭: cat 전체 문자열을 ETF 이름에서 탐색 (2글자 슬라이싱보다 안전)
        env_key       = next((k for k in sector_env if cat in k), None)
        sector_status = sector_env.get(env_key, "상태 불명")
        if env_key is None:
            print(f"[Main] '{cat}' 섹터 ETF 매칭 실패 → 상태 불명 처리")

        res = analyze_stock(name, ticker, sector_status)
        if not res:
            continue

        # 사용자 피드백(#기록) 매칭
        comment = ""
        c_name  = name.replace(" ", "")
        for log in user_logs:
            if c_name in log['clean']:
                comment = log['raw']

        # 리포트 라인 조립 (reason도 escape 처리)
        msg = (
            f"• <b>[{html.escape(cat)}] {html.escape(name)}</b>\n"
            f"  - 현재가: {res['current']:,}원 | 타점: <b>{res['entry']:,}원</b> | 손절: {res['stop']:,}원\n"
            f"  - 사유: {html.escape(res['reason'])}"
        )
        if "매수" in res['action']:
            report_buy.append(msg)
        else:
            report_wait.append(msg)

        trading_rows.append([
            datetime.now().strftime("%Y-%m-%d"),
            cat, name,
            res['current'], res['entry'], res['stop'],
            res['action'], res['reason'], comment
        ])

    # ── 3. 보고서 조립 및 전송 ───────────
    full_msg = (
        "🚨 <b>[V3.1 SCM 스윙 엔진 리포트]</b>\n\n"
        "📊 <b>[섹터 환경]</b>\n"
        + "\n".join(report_etf) + "\n\n"
        "🚀 <b>[신규 발주 (매수)]</b>\n"
        + ("\n".join(report_buy) if report_buy else "• 조건 충족 없음") + "\n\n"
        "⏳ <b>[입고 대기]</b>\n"
        + ("\n".join(report_wait) if report_wait else "• 해당 없음")
    )
    send_telegram_with_retry(full_msg)

    # ── 4. Google Sheets 저장 ────────────
    if trading_rows:
        service.values().append(
            spreadsheetId=SHEET_ID,
            range=f"'{TARGET_TAB}'!A2",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": trading_rows}
        ).execute()
        print(f"[Sheets] {len(trading_rows)}건 저장 완료")

    print("[Success] V3.1 공정 완료")


if __name__ == "__main__":
    main()
