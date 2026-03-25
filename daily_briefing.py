import os
import asyncio
import pandas as pd
import FinanceDataReader as fdr
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime, timedelta

# 1. 환경 설정 로드
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# 2. SCM 최적화: 외부 서버(KRX) 차단 원천 봉쇄 (Local Mapping)
MY_PORTFOLIO = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380"
}

# 3. 정밀도 향상: EMA 기반 RSI 계산
def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# 4. 안정성 확보: 텔레그램 4096자 제한 방어 (안전하게 4000자로 분할)
async def send_message_safe(bot, text):
    MAX_LEN = 4000
    chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]
    for chunk in chunks:
        await bot.send_message(chat_id=CHAT_ID, text=chunk, parse_mode='HTML')

# 5. 핵심 파이프라인
async def send_briefing():
    bot = Bot(token=TELEGRAM_TOKEN)
    full_report = "📅 <b>오늘의 시장 자동 분석 리포트</b>\n" + "━"*25 + "\n"

    # 조달 최적화: 최근 120일치 데이터만 로드
    start_date = (datetime.today() - timedelta(days=120)).strftime('%Y-%m-%d')

    for stock_name, stock_code in MY_PORTFOLIO.items():
        print(f"🔍 [{stock_name}] 주가 데이터 직접 조달 중...")
        try:
            df = fdr.DataReader(stock_code, start_date).tail(60).copy()
            if len(df) < 20:
                raise ValueError("데이터 부족")

            df['RSI'] = calculate_rsi(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 결함 방어: NaN 값 철저 검증
            if pd.isna(curr['Close']) or pd.isna(prev['Close']):
                raise ValueError("종가 데이터 없음")

            rsi_val = curr['RSI']
            if pd.isna(rsi_val):
                raise ValueError("RSI 연산 불가 (거래정지 등 변동성 0 상태)")

            c_price = int(curr['Close'])
            c_percent = ((c_price - int(prev['Close'])) / int(prev['Close'])) * 100

            prompt = f"""
            당신은 펀드매니저입니다. [{stock_name}] 현재가 {c_price:,.0f}원({c_percent:+.2f}%), RSI {rsi_val:.1f}.
            이 지표를 바탕으로 오늘의 대응 전략을 1~2줄로 명확하게 평문으로 작성하세요. (특수기호 금지)
            """
            response = await asyncio.to_thread(model.generate_content, prompt)

            full_report += f"\n📌 <b>{stock_name}</b>\n"
            full_report += f"  • 현재가: {c_price:,.0f}원 ({c_percent:+.2f}%)\n"
            full_report += f"  • RSI(14): {rsi_val:.1f}\n"
            full_report += f"  • 💡 AI 코멘트: {response.text.strip()}\n"

        except Exception as e:
            full_report += f"\n❌ <b>{stock_name}</b>: 분석 실패 ({str(e)})\n"

    await send_message_safe(bot, full_report)
    print("✅ 데일리 리포트 전송 완료!")

if __name__ == "__main__":
    asyncio.run(send_briefing())
