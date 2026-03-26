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

SHEET_URL = "https://docs.google.com/spreadsheets/d/1yApGhO57y_sWM30FbWWV44R2a3LhUomQvH7WloZTDmw/edit"

# 2. 다이나믹 섹터 매핑 딕셔너리
ETF_MAPPING = {
    "반도체": ("091160", "KODEX 반도체"),
    "전자": ("091160", "KODEX 반도체"),
    "자동차": ("091180", "KODEX 자동차"),
    "차량": ("091180", "KODEX 자동차"),
    "바이오": ("261240", "KODEX 헬스케어"),
    "의약": ("261240", "KODEX 헬스케어"),
    "제약": ("261240", "KODEX 헬스케어"),
    "생명": ("261240", "KODEX 헬스케어"),
    "은행": ("091220", "KODEX 은행"),
    "금융": ("091220", "KODEX 은행"),
    "철강": ("117680", "KODEX 철강"),
    "금속": ("117680", "KODEX 철강"),
    "전지": ("305720", "KODEX 2차전지산업"),
    "화학": ("305720", "KODEX 2차전지산업"),
    "소프트웨어": ("139260", "TIGER 소프트웨어"),
    "게임": ("157440", "TIGER 게임"),
    "인터넷": ("139260", "TIGER 소프트웨어"),
    "엔터": ("227560", "KODEX 미디어&엔터테인먼트"),
    "조선": ("091210", "KODEX 조선")
}

# 3. 기술적 지표 연산
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

# 4. 핵심 파이프라인
async def send_briefing():
    bot = Bot(token=TELEGRAM_TOKEN)
    today_str = datetime.today().strftime('%Y-%m-%d')
    full_report = f"📅 <b>{today_str} 시장 자동 분석 리포트 (V5.0)</b>\n" + "━"*25 + "\n"
    log_data = []
    
    # [A] 구글 시트에서 포트폴리오 읽어오기
    try:
        creds_dict = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
        client = gspread.service_account_from_dict(creds_dict)
        doc = client.open_by_url(SHEET_URL)
        portfolio_ws = doc.worksheet("Portfolio")
        
        raw_stocks = portfolio_ws.col_values(1)[1:]
        my_stocks = [s.replace(" ", "").upper() for s in raw_stocks if s.strip()]
        
        if not my_stocks:
            raise ValueError("Portfolio 탭에 입력된 종목이 없습니다.")
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 치명적 오류: 구글 시트 'Portfolio' 탭 읽기 실패\n{e}")
        return

    # [B] KRX 마스터 명단 1회 적재
    print("⏳ KRX 마스터 데이터 적재 중...")
    try:
        krx_df = fdr.StockListing('KRX')
        krx_df['Name_Clean'] = krx_df['Name'].str.replace(" ", "", regex=False).str.upper()
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 KRX 마스터 데이터 로딩 실패: {e}")
        return

    start_date = (datetime.today() - timedelta(days=150)).strftime('%Y-%m-%d')

    # [C] 종목별 분석 루프
    for search_name in my_stocks:
        print(f"🔍 [{search_name}] 분석 중...")
        stock_name_original = search_name
        try:
            # 1. 자동 종목 매핑
            stock_row = krx_df[krx_df['Name_Clean'] == search_name]
            if stock_row.empty:
                raise ValueError("상장폐지 되었거나 이름을 잘못 입력했습니다.")
            
            stock_code = stock_row['Code'].values[0]
            stock_name_original = stock_row['Name'].values[0]
            
            # (KeyError 방어 패치 적용) .get()으로 안전하게 접근 후 종목명 결합
            industry_val = stock_row.get('Industry', pd.Series([""])).values[0]
            sector_val   = stock_row.get('Sector',   pd.Series([""])).values[0]
            industry_str = str(industry_val) + str(sector_val) + stock_name_original
            market_type  = stock_row['Market'].values[0]

            sector_code, sector_name = None, None
            for key, (ecode, ename) in ETF_MAPPING.items():
                if key in industry_str:
                    sector_code, sector_name = ecode, ename
                    break
            
            if not sector_code:
                sector_code, sector_name = ("069500", "KODEX 200") if market_type == 'KOSPI' else ("114800", "KODEX 코스닥150")

            # 2. 데이터 조달
            df_stock  = fdr.DataReader(stock_code,  start_date).copy()
            df_sector = fdr.DataReader(sector_code, start_date).copy()

            if len(df_stock) < 65 or len(df_sector) < 65:
                raise ValueError("신규 상장 등 지표 연산용 데이터가 부족합니다.")

            # 3. 지표 가공
            df_stock  = calculate_indicators(df_stock)
            df_sector['MA60'] = df_sector['Close'].rolling(window=60).mean()

            curr_s   = df_stock.iloc[-1]
            prev_s   = df_stock.iloc[-2]
            curr_sec = df_sector.iloc[-1]

            # (MA60 추가된 완벽한 NaN 검증 패치 적용)
            if (pd.isna(curr_s['Close']) or pd.isna(prev_s['Close']) or
                pd.isna(curr_s['RSI'])   or pd.isna(curr_s['MA60'])   or
                pd.isna(curr_s['BB_Width']) or pd.isna(curr_sec['MA60'])):
                raise ValueError("결측치(NaN) 발생으로 연산 불가")

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
            vol_msg    = "⚠️ <b>[변동성 경고] 비중 축소</b>" if volatility_warn else "✅ 안정적"
            sector_msg = "상승 추세" if sector_trend_ok else "하락 추세 (보수적 접근)"

            prompt = f"""
            당신은 펀드매니저입니다. [{stock_name_original}] 현재가 {c_price:,.0f}원({c_percent:+.2f}%), RSI {rsi_val:.1f}, 60일선 돌파: {stock_trend_ok}.
            자동 판별된 산업군({sector_name}) 상태: {sector_msg}.
            이 지표를 바탕으로 오늘의 대응 전략을 1~2줄로 명확하게 평문으로 작성하세요.
            """
            response   = await asyncio.to_thread(model.generate_content, prompt)
            ai_comment = html.escape(response.text.strip())

            full_report += f"\n📌 <b>{stock_name_original}</b> (산업군: {sector_name} - {sector_msg})\n"
            full_report += f"  • 현재가: {c_price:,.0f}원 ({c_percent:+.2f}%)\n"
            full_report += f"  • RSI(14): {rsi_val:.1f} | 60MA 상회: {'O' if stock_trend_ok else 'X'}\n"
            full_report += f"  • 시그널: {status_msg} | 리스크: {vol_msg}\n"
            full_report += f"  • 💡 AI 코멘트: {ai_comment}\n"

            # 성공 로그 기록
            log_data.append([
                today_str, stock_name_original, c_price, round(rsi_val, 2),
                round(bb_width, 4), str(volatility_warn),
                str(sector_trend_ok), str(buy_signal), ""
            ])

        except Exception as e:
            err_str = str(e)
            full_report += f"\n❌ <b>{stock_name_original}</b>: 분석 실패 ({err_str})\n"
            # 실패 로그 기록
            log_data.append([
                today_str, stock_name_original, "ERROR", "ERROR", 
                "ERROR", "ERROR", "ERROR", "ERROR", err_str
            ])

        finally:
            await asyncio.sleep(3)

    # [D] 구글 시트 영구 기록
    await send_message_safe(bot, full_report)

    if log_data:
        try:
            worksheet = doc.worksheet("Trade_Log")
            first_cell = worksheet.acell('A1').value
            if not first_cell or str(first_cell).strip() == "":
                headers = ["Date", "Stock", "Close", "RSI", "BB_Width", "Volatility_Warn", "Sector_Up", "Buy_Signal", "Error_Reason"]
                worksheet.append_row(headers)
                
            worksheet.append_rows(log_data)
            print("✅ 구글 시트(Trade_Log) 영구 기록 완료!")
        except Exception as e:
            await bot.send_message(chat_id=CHAT_ID, text=f"❌ 구글 시트 기록 실패: {e}")

    print("✅ V5.0 완전 자동화 리포트 전송 완료!")

if __name__ == "__main__":
    asyncio.run(send_briefing())
