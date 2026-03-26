import os
import html
import json
import asyncio
import pandas as pd
import FinanceDataReader as fdr
import google.generativeai as genai
import gspread
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime, timedelta

# 1. 환경 설정
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# 구글 시트 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1yApGhO57y_sWM30FbWWV44R2a3LhUomQvH7WloZTDmw/edit"

# 2. 마스터 데이터
MY_PORTFOLIO = {
    "삼성전자":   ("005930", "091160", "KODEX 반도체"),
    "SK하이닉스": ("000660", "091160", "KODEX 반도체"),
    "현대차":     ("005380", "091180", "KODEX 자동차")
}

# 3. 기술적 지표 일괄 연산
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain  = delta.where(delta > 0, 0)
    loss  = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss

    df['RSI']      = 100 - (100 / (1 + rs))
    df['MA60']     = df['Close'].rolling(window=60).mean()
    df['MA20']     = df['Close'].rolling(window=20).mean()
    df['STD20']    = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['MA20']
    return df

# 4. 텔레그램 분할 전송
def split_by_lines(text, max_len=4000):
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)
    return chunks

async def send_message_safe(bot, text):
    for chunk in split_by_lines(text):
        await bot.send_message(chat_id=CHAT_ID, text=chunk, parse_mode='HTML')

# 5. 핵심 브리핑 파이프라인
async def send_briefing():
    bot = Bot(token=TELEGRAM_TOKEN)
    today_str   = datetime.today().strftime('%Y-%m-%d')
    full_report = f"📅 <b>{today_str} 장 마감 자동 분석 리포트 (V4.1)</b>\n" + "━"*25 + "\n"
    log_data    = []
    
    start_date  = (datetime.today() - timedelta(days=150)).strftime('%Y-%m-%d')

    for stock_name, (stock_code, sector_code, sector_name) in MY_PORTFOLIO.items():
        print(f"🔍 [{stock_name}] 분석 중...")
        try:
            df_stock  = fdr.DataReader(stock_code,  start_date).copy()
            df_sector = fdr.DataReader(sector_code, start_date).copy()

            if len(df_stock) < 65 or len(df_sector) < 65:
                raise ValueError("지표 연산용 데이터 부족")

            df_stock  = calculate_indicators(df_stock)
            df_sector['MA60'] = df_sector['Close'].rolling(window=60).mean()

            curr_s   = df_stock.iloc[-1]
            prev_s   = df_stock.iloc[-2]
            curr_sec = df_sector.iloc[-1]

            if pd.isna(curr_s['Close']) or pd.isna(prev_s['Close']):
                raise ValueError("종가 데이터 누락 (NaN)")
            for col in ['RSI', 'MA60', 'BB_Width']:
                if pd.isna(curr_s[col]):
                    raise ValueError(f"{col} 연산 실패 (NaN)")
            if pd.isna(curr_sec['MA60']):
                raise ValueError("섹터 ETF MA60 연산 실패 (NaN)")

            prev_price = float(prev_s['Close'])
            c_percent  = ((float(curr_s['Close']) - prev_price) / prev_price) * 100
            c_price    = int(curr_s['Close'])
            rsi_val    = curr_s['RSI']
            bb_width   = curr_s['BB_Width']

            sector_trend_ok = curr_sec['Close'] > curr_sec['MA60']
            stock_trend_ok  = c_price > curr_s['MA60']
            stock_rsi_ok    = rsi_val < 40

            buy_signal      = sector_trend_ok and stock_trend_ok and stock_rsi_ok
            volatility_warn = bb_width > 0.20

            status_msg = "🟢 <b>매수 조건 충족 (최적 발주점)</b>" if buy_signal else "⏳ 관망 (조건 미달)"
            vol_msg    = "⚠️ <b>[변동성 경고] 비중 50% 축소 권장</b>" if volatility_warn else "✅ 안정적 변동성"
            sector_msg = "상승 추세" if sector_trend_ok else "하락 추세 (보수적 접근)"

            prompt = f"""
            당신은 펀드매니저입니다. [{stock_name}] 데이터: 현재가 {c_price:,.0f}원({c_percent:+.2f}%), RSI {rsi_val:.1f}, 60일선 돌파 여부: {stock_trend_ok}.
            소속 산업군({sector_name}) 상태: {sector_msg}.
            이 지표를 바탕으로 오늘의 대응 전략을 1~2줄로 명확하게 평문으로 작성하세요. (특수기호 금지)
            """
            response   = await asyncio.to_thread(model.generate_content, prompt)
            ai_comment = html.escape(response.text.strip())

            full_report += f"\n📌 <b>{stock_name}</b> (산업군: {sector_name} - {sector_msg})\n"
            full_report += f"  • 현재가: {c_price:,.0f}원 ({c_percent:+.2f}%)\n"
            full_report += f"  • RSI(14): {rsi_val:.1f} | 60MA 상회: {'O' if stock_trend_ok else 'X'}\n"
            full_report += f"  • 시그널: {status_msg}\n"
            full_report += f"  • 리스크: {vol_msg}\n"
            full_report += f"  • 💡 AI 코멘트: {ai_comment}\n"

            log_data.append([
                today_str, stock_name, c_price, round(rsi_val, 2),
                round(bb_width, 4), str(volatility_warn),
                str(sector_trend_ok), str(buy_signal)
            ])

        except Exception as e:
            full_report += f"\n❌ <b>{stock_name}</b>: 분석 실패 ({str(e)})\n"

        finally:
            await asyncio.sleep(3)

    # 6. 전송 및 구글 시트 영구 로깅
    await send_message_safe(bot, full_report)

    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if creds_json and log_data:
        try:
            creds_dict = json.loads(creds_json)
            client = gspread.service_account_from_dict(creds_dict)
            doc = client.open_by_url(SHEET_URL)
            worksheet = doc.worksheet("Trade_Log")
            
            # 헤더 중복 방지 (A1 셀 명시적 확인)
            first_cell = worksheet.acell('A1').value
            if not first_cell or str(first_cell).strip() == "":
                headers = ["Date", "Stock", "Close", "RSI", "BB_Width", "Volatility_Warn", "Sector_Up", "Buy_Signal"]
                worksheet.append_row(headers)
                
            # 데이터 적재
            worksheet.append_rows(log_data)
            print("✅ 구글 시트(Trade_Log) 영구 기록 완료!")
            
        except Exception as e:
            err_msg = f"❌ 구글 시트 통신/기록 실패: {e}"
            print(err_msg)
            # 장애 발생 시 텔레그램으로 관리자 즉시 호출 (안돈 시스템)
            await bot.send_message(chat_id=CHAT_ID, text=err_msg)

    print("✅ V4.1 데이터베이스 연동 및 결산 리포트 전송 완료!")

if __name__ == "__main__":
    asyncio.run(send_briefing())
