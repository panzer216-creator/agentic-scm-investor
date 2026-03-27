import os
import html
import json
import asyncio
import feedparser
import pandas as pd
import FinanceDataReader as fdr
import google.generativeai as genai
import gspread
import OpenDartReader
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime, timedelta

# ==========================================
# 1. 인프라 및 환경 설정
# ==========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DART_API_KEY = os.getenv("DART_API_KEY")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

SHEET_URL = "https://docs.google.com/spreadsheets/d/1yApGhO57y_sWM30FbWWV44R2a3LhUomQvH7WloZTDmw/edit"

# [패치 완료] DART API 초기화 크래시 방어
try:
    dart = OpenDartReader(DART_API_KEY) if DART_API_KEY else None
except Exception as e:
    print(f"⚠️ DART API 초기화 실패: {e}")
    dart = None

ETF_MAPPING = {
    "반도체": "091160", "자동차": "091180", "바이오": "261240", "의약": "261240",
    "은행": "091220", "철강": "117680", "전지": "305720", "화학": "305720",
    "소프트웨어": "139260", "게임": "157440", "엔터": "227560", "조선": "091210"
}

# ==========================================
# 2. 분석 엔진 (기술적 지표 + 팩터 계산)
# ==========================================
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))

    df['MA60'] = df['Close'].rolling(window=60).mean()

    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean().shift(1)
    return df

def get_recent_news(stock_name):
    url = f"https://news.google.com/rss/search?q={stock_name}+when:7d&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(url)
        return [entry.title for entry in feed.entries[:5]]
    except:
        return []

def get_recent_dart(stock_code):
    if not dart: return []
    try:
        start_dt = (datetime.today() - timedelta(days=7)).strftime('%Y%m%d')
        filings = dart.list(stock_code, start=start_dt)
        if filings is None or filings.empty: return []
        return filings['report_nm'].head(5).tolist()
    except:
        return []

def split_by_lines(text, max_len=4000):
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line + "\n"
        else: current += line + "\n"
    if current: chunks.append(current)
    return chunks

async def send_message_safe(bot, text):
    for chunk in split_by_lines(text):
        await bot.send_message(chat_id=CHAT_ID, text=chunk, parse_mode='HTML')

# ==========================================
# 3. 메인 파이프라인 (V6.0)
# ==========================================
async def send_briefing():
    bot = Bot(token=TELEGRAM_TOKEN)
    today_str = datetime.today().strftime('%Y-%m-%d')
    full_report = f"📅 <b>{today_str} 퀀트 통합 브리핑 (V6.0)</b>\n" + "━"*25 + "\n"
    log_data = []
    
    try:
        creds_dict = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
        client = gspread.service_account_from_dict(creds_dict)
        doc = client.open_by_url(SHEET_URL)
        portfolio_ws = doc.worksheet("Portfolio")
        
        raw_data = portfolio_ws.get_all_values()[1:]
        my_stocks = []
        for row in raw_data:
            if not row or not row[0].strip(): continue
            stock_name = row[0].replace(" ", "").upper()
            custom_etf = row[1].strip() if len(row) > 1 else ""
            my_stocks.append((stock_name, custom_etf))
            
        if not my_stocks: raise ValueError("Portfolio 비어있음")
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 시트 연동 실패\n{html.escape(str(e))}")
        return

    print("⏳ KRX 마스터 데이터 적재 중...")
    try:
        krx_df = fdr.StockListing('KRX')
        krx_df['Name_Clean'] = krx_df['Name'].str.replace(" ", "", regex=False).str.upper()
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 KRX 연동 실패\n{html.escape(str(e))}")
        return

    start_date = (datetime.today() - timedelta(days=150)).strftime('%Y-%m-%d')

    for search_name, custom_etf in my_stocks:
        print(f"🔍 [{search_name}] 다차원 분석 중...")
        try:
            stock_row = krx_df[krx_df['Name_Clean'] == search_name]
            if stock_row.empty: raise ValueError("상장폐지 또는 종목명 오류")
            
            stock_code = stock_row['Code'].values[0]
            stock_name_original = stock_row['Name'].values[0]
            
            sector_code = None
            if custom_etf:
                etf_row = krx_df[krx_df['Name_Clean'] == custom_etf.replace(" ", "").upper()]
                if not etf_row.empty: sector_code = etf_row['Code'].values[0]
            
            if not sector_code:
                industry_str = str(stock_row.get('Industry', pd.Series([""])).values[0]) + str(stock_row.get('Sector', pd.Series([""])).values[0])
                for key, ecode in ETF_MAPPING.items():
                    if key in industry_str or key in stock_name_original:
                        sector_code = ecode
                        break
                if not sector_code: sector_code = "069500"

            df_stock  = fdr.DataReader(stock_code,  start_date)
            df_sector = fdr.DataReader(sector_code, start_date)
            if len(df_stock) < 65 or len(df_sector) < 65: raise ValueError("데이터 부족")

            df_stock  = calculate_indicators(df_stock)
            df_sector['MA60'] = df_sector['Close'].rolling(window=60).mean()

            curr_s = df_stock.iloc[-1]
            prev_s = df_stock.iloc[-2]
            
            # [패치 완료] Signal 포함 다중 NaN 철저 검증
            if (pd.isna(curr_s['Close'])  or pd.isna(prev_s['Close'])  or
                pd.isna(curr_s['MA60'])   or pd.isna(curr_s['MACD'])   or
                pd.isna(curr_s['Signal']) or pd.isna(prev_s['Signal']) or
                pd.isna(curr_s['RSI'])    or pd.isna(df_sector.iloc[-1]['MA60'])):
                raise ValueError("지표 연산 실패(NaN)")

            c_price = int(curr_s['Close'])
            prev_price = float(prev_s['Close'])
            
            # --- [팩터 스코어링 산출] ---
            score = 0
            
            # 1. 거시 업황 추세 (Max 20)
            stock_up = c_price > curr_s['MA60']
            sector_up = df_sector.iloc[-1]['Close'] > df_sector.iloc[-1]['MA60']
            if stock_up and sector_up: score += 20
            elif stock_up or sector_up: score += 10

            # 2. 타점 및 가속도 (Max 30)
            rsi_3d_min = df_stock['RSI'].iloc[-3:].min()
            if rsi_3d_min < 40: score += 15
            
            macd_cross = (prev_s['MACD'] <= prev_s['Signal']) and (curr_s['MACD'] > curr_s['Signal'])
            if macd_cross: score += 15

            # 3. 수요 폭발 에너지 (Max 20)
            is_yangbong = c_price > prev_price
            
            # [패치 완료] Vol_MA5 초기 결측치 우회
            if pd.notna(curr_s['Vol_MA5']) and (curr_s['Volume'] > curr_s['Vol_MA5'] * 2) and is_yangbong: 
                score += 10
            
            # [패치 완료] 상장주식수 ZeroDivisionError 방어
            listed_shares = stock_row['Stocks'].values[0]
            if not listed_shares or pd.isna(listed_shares) or int(listed_shares) == 0:
                turnover_ratio = 0.0
            else:
                turnover_ratio = (curr_s['Volume'] / int(listed_shares)) * 100
                
            if turnover_ratio >= 2.0 and is_yangbong: score += 10

            # 4. 펀더멘털 판독 (AI 통합, Max 30)
            news_list = get_recent_news(stock_name_original)
            dart_list = get_recent_dart(stock_code)
            
            prompt = f"""
            주식: {stock_name_original}
            최근 DART 공시: {dart_list}
            최근 뉴스: {news_list}
            현재가: {c_price}원, 기술적 타점 점수: {score}/70
            
            위 사실을 바탕으로 기업의 펀더멘털 상태를 판독하고, 반드시 아래 JSON 양식으로만 답변하세요.
            1. 치명적 악재(유상증자, 소송, 횡령, 상장폐지 사유 등 핵심 경쟁력 훼손)가 있다면 score를 0으로 설정.
            2. 유의미한 호재(단일판매공급계약, 흑자전환, 호실적)가 있다면 score를 30으로 설정.
            3. 평범한 수준이거나 노이즈성 기사만 있다면 score를 15로 설정.
            
            형식: {{"score": 정수, "comment": "펀더멘털 평가 1줄 요약"}}
            """
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            # [패치 완료] JSON 파싱 실패 시 무중단 Fallback
            try:
                ai_data = json.loads(response.text.strip())
            except (json.JSONDecodeError, ValueError):
                ai_data = {"score": 15, "comment": "AI 응답 파싱 실패 (중립 처리)"}
                
            fund_score = int(ai_data.get('score', 15))
            
            # [패치 완료] AI 코멘트 HTML 이스케이프
            fund_comment = html.escape(ai_data.get('comment', '분석 실패'))
            
            # --- [최종 등급 산출] ---
            total_score = score + fund_score
            if fund_score == 0:
                rating = "🚨 매도 (Kill Switch)"
                total_score = 0
            elif total_score >= 80: rating = "🔥 강력 매수"
            elif total_score >= 60: rating = "🟢 매수 (분할)"
            elif total_score >= 40: rating = "⏳ 관망 (Hold)"
            else: rating = "⚠️ 비중 축소"

            full_report += f"\n📌 <b>{stock_name_original}</b> | 총점: <b>{total_score}점</b> ({rating})\n"
            full_report += f"  • 현재가: {c_price:,.0f}원 | 회전율: {turnover_ratio:.1f}%\n"
            full_report += f"  • 기술점수: {score}/70 | 펀더멘털: {fund_score}/30\n"
            full_report += f"  • 💡 AI 판독: {fund_comment}\n"

            log_data.append([
                today_str, stock_name_original, total_score, rating,
                c_price, round(curr_s['RSI'], 1), str(macd_cross),
                round(turnover_ratio, 2), fund_score, fund_comment, ""
            ])

        except Exception as e:
            err_str = str(e)
            # [패치 완료] 에러 메시지 HTML 이스케이프
            full_report += f"\n❌ <b>{search_name}</b>: 에러 ({html.escape(err_str)})\n"
            log_data.append([today_str, search_name, "ERROR", "ERROR", "", "", "", "", "", "", err_str])

        finally:
            await asyncio.sleep(4)

    await send_message_safe(bot, full_report)

    if log_data:
        try:
            worksheet = doc.worksheet("Trade_Log")
            first_cell = worksheet.acell('A1').value
            if not first_cell or str(first_cell).strip() == "":
                headers = ["Date", "Stock", "Total_Score", "Rating", "Close", "RSI", "MACD_Cross", "Turnover_Ratio", "Fund_Score", "AI_Comment", "Error_Reason"]
                worksheet.append_row(headers)
            worksheet.append_rows(log_data)
            print("✅ V6.0 구글 시트 영구 기록 완료!")
        except Exception as e:
            await bot.send_message(chat_id=CHAT_ID, text=f"❌ 구글 시트 기록 실패: {html.escape(str(e))}")

if __name__ == "__main__":
    asyncio.run(send_briefing())
