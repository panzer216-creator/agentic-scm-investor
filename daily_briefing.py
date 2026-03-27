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
# [패치 1] 공정 분리: JSON 강제 모델과 텍스트 전용 모델을 독립적으로 선언
model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
model_text = genai.GenerativeModel('gemini-2.5-flash')

SHEET_URL = "https://docs.google.com/spreadsheets/d/1yApGhO57y_sWM30FbWWV44R2a3LhUomQvH7WloZTDmw/edit"

# DART API 초기화 크래시 방어 (V6.0 패치 유지)
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
# 2. 분석 엔진 모듈
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

# 기간별 뉴스 스캐너 (장기 3m / 단기 7d 분리 가능)
def get_news(stock_name, period="7d", limit=5):
    url = f"https://news.google.com/rss/search?q={stock_name}+when:{period}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(url)
        return [entry.title for entry in feed.entries[:limit]]
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
# 3. 메인 파이프라인 (V7.0 듀얼 엔진)
# ==========================================
async def send_briefing():
    bot = Bot(token=TELEGRAM_TOKEN)
    today_str = datetime.today().strftime('%Y-%m-%d')
    full_report = f"📅 <b>{today_str} 퀀트 통합 브리핑 (V7.0)</b>\n" + "━"*30 + "\n"
    log_data = []
    
    # [A] 구글 시트 연동 및 데이터 적재
    try:
        creds_dict = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
        client = gspread.service_account_from_dict(creds_dict)
        doc = client.open_by_url(SHEET_URL)
        portfolio_ws = doc.worksheet("Portfolio")
        
        raw_data = portfolio_ws.get_all_values()
        header = raw_data[0]
        # C열(Core_Momentum) 헤더 자동 생성 방어
        if len(header) < 3 or header[2] != "Core_Momentum":
            portfolio_ws.update_cell(1, 3, "Core_Momentum")
            raw_data = portfolio_ws.get_all_values()
            
        rows = raw_data[1:]
        my_stocks = []
        for i, row in enumerate(rows):
            if not row or not row[0].strip(): continue
            stock_name = row[0].replace(" ", "").upper()
            custom_etf = row[1].strip() if len(row) > 1 else ""
            core_momentum = row[2].strip() if len(row) > 2 else ""
            my_stocks.append({"row_idx": i+2, "name": stock_name, "etf": custom_etf, "momentum": core_momentum})
            
        if not my_stocks: raise ValueError("Portfolio 비어있음")
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 시트 연동 실패\n{html.escape(str(e))}")
        return

    # [B] S&OP 장기 엔진: 빈칸 모멘텀 자동 추출 및 Batch 기록
    print("⏳ 장기 모멘텀(3개월) 스캐닝 중...")
    momentum_updates = []
    for stock in my_stocks:
        if not stock["momentum"]: # C열이 비어있을 때만 가동 (트리거)
            long_term_news = get_news(stock["name"], period="3m", limit=10)
            if long_term_news:
                prompt_m = f"""
                주식: {stock["name"]}
                최근 3개월 핵심 뉴스: {long_term_news}
                위 뉴스를 분석하여, 향후 이 기업의 주가를 견인할 '가장 강력한 중장기 핵심 모멘텀(수주, 신작, 임상, 실적 등)'을 20자 이내의 단답형 평문으로 하나만 추출하세요. JSON 말고 그냥 텍스트만 출력하세요.
                """
                # [패치 1 반영] 텍스트 전용 모델(model_text) 사용으로 JSON 파싱 충돌 원천 차단
                res_m = await asyncio.to_thread(model_text.generate_content, prompt_m)
                extracted_momentum = res_m.text.strip().replace('"', '').replace('\n', ' ')
                stock["momentum"] = extracted_momentum
                momentum_updates.append({'range': f'C{stock["row_idx"]}', 'values': [[extracted_momentum]]})
                await asyncio.sleep(2)

    # API 과부하 방지를 위한 일괄 저장 (Batch Update)
    if momentum_updates:
        try:
            portfolio_ws.batch_update(momentum_updates)
            print(f"✅ {len(momentum_updates)}개 종목의 장기 모멘텀 세팅 완료")
        except Exception as e:
            print(f"⚠️ 모멘텀 시트 저장 실패: {e}")

    # [C] KRX 마스터 데이터 적재
    print("⏳ KRX 마스터 데이터 적재 중...")
    try:
        krx_df = fdr.StockListing('KRX')
        krx_df['Name_Clean'] = krx_df['Name'].str.replace(" ", "", regex=False).str.upper()
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"🚨 KRX 연동 실패\n{html.escape(str(e))}")
        return

    start_date = (datetime.today() - timedelta(days=150)).strftime('%Y-%m-%d')

    # [D] MRP 단기 진척도 트래킹 엔진 (일일 루프)
    for stock in my_stocks:
        search_name = stock["name"]
        print(f"🔍 [{search_name}] 일일 진척도 분석 중...")
        try:
            stock_row = krx_df[krx_df['Name_Clean'] == search_name]
            if stock_row.empty: raise ValueError("상장폐지 또는 종목명 오류")
            
            stock_code = stock_row['Code'].values[0]
            stock_name_original = stock_row['Name'].values[0]
            
            sector_code = None
            if stock["etf"]:
                etf_row = krx_df[krx_df['Name_Clean'] == stock["etf"].replace(" ", "").upper()]
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
            
            # (V6.0 패치 유지) 다중 결측치(NaN) 완벽 검증
            if (pd.isna(curr_s['Close'])  or pd.isna(prev_s['Close'])  or
                pd.isna(curr_s['MA60'])   or pd.isna(curr_s['MACD'])   or
                pd.isna(curr_s['Signal']) or pd.isna(prev_s['Signal']) or
                pd.isna(curr_s['RSI'])    or pd.isna(df_sector.iloc[-1]['MA60'])):
                raise ValueError("지표 연산 실패(NaN)")

            c_price = int(curr_s['Close'])
            prev_price = float(prev_s['Close'])
            
            # --- [기술적 팩터 산출] ---
            score = 0
            
            stock_up = c_price > curr_s['MA60']
            sector_up = df_sector.iloc[-1]['Close'] > df_sector.iloc[-1]['MA60']
            if stock_up and sector_up: score += 20
            elif stock_up or sector_up: score += 10

            rsi_3d_min = df_stock['RSI'].iloc[-3:].min()
            if rsi_3d_min < 40: score += 15
            
            macd_cross = (prev_s['MACD'] <= prev_s['Signal']) and (curr_s['MACD'] > curr_s['Signal'])
            if macd_cross: score += 15

            is_yangbong = c_price > prev_price
            # (V6.0 패치 유지) Vol_MA5 NaN 방어
            if pd.notna(curr_s['Vol_MA5']) and (curr_s['Volume'] > curr_s['Vol_MA5'] * 2) and is_yangbong: 
                score += 10
            
            # (V6.0 패치 유지) ZeroDivisionError 방어
            listed_shares = stock_row['Stocks'].values[0]
            turnover_ratio = 0.0 if not listed_shares or pd.isna(listed_shares) or int(listed_shares) == 0 else (curr_s['Volume'] / int(listed_shares)) * 100
            if turnover_ratio >= 2.0 and is_yangbong: score += 10

            # --- [펀더멘털 & 모멘텀 AI 통합 판독] ---
            news_list = get_news(stock_name_original, period="7d", limit=5)
            dart_list = get_recent_dart(stock_code)
            tracked_momentum = stock["momentum"]
            
            prompt = f"""
            주식: {stock_name_original}
            추적 중인 핵심 모멘텀: [{tracked_momentum}]
            최근 7일 DART 공시: {dart_list}
            최근 7일 뉴스: {news_list}
            
            위 정보를 바탕으로 기업 상태를 진단하고 반드시 아래 JSON 양식으로 출력하세요.
            1. 치명적 악재(상장폐지 사유, 유상증자 등)이거나, 기존 모멘텀이 완전히 소멸되었다면 score를 0으로 설정(매도).
            2. 주가는 급등했으나 실적/수주 팩트 없이 단순 테마에 의한 '오버슈팅(거품)' 구간이라면 score를 10으로 설정.
            3. 유의미한 호재(수주, 흑자전환)이거나 모멘텀이 순항 중이면 score를 30으로 설정.
            4. 그 외 평범한 상태라면 score를 15로 설정.
            
            형식: {{"score": 정수, "fact_check": "최근 1주일 공시/실적 팩트 1줄 요약", "momentum_status": "추적 중인 핵심 모멘텀의 현재 진척 상황 및 시장 기대치 2줄 평가"}}
            """
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            # (V6.0 패치 유지) 무중단 Fallback
            try:
                ai_data = json.loads(response.text.strip())
            except (json.JSONDecodeError, ValueError):
                ai_data = {"score": 15, "fact_check": "API 지연", "momentum_status": "AI 판독 불가(중립 유지)"}
                
            fund_score = int(ai_data.get('score', 15))
            
            # [패치 2 반영] 시트 저장용 Raw Data와 텔레그램 출력용 Escaped Data 분리
            fact_raw = ai_data.get('fact_check', '내용 없음')
            momentum_raw = ai_data.get('momentum_status', '내용 없음')
            
            fact_txt = html.escape(fact_raw)
            momentum_txt = html.escape(momentum_raw)
            
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
            full_report += f"  • <b>핵심 모멘텀:</b> {html.escape(tracked_momentum)}\n"
            full_report += f"  • 현재가: {c_price:,.0f}원 | 회전율: {turnover_ratio:.1f}%\n"
            full_report += f"  • 기술점수: {score}/70 | 펀더멘털: {fund_score}/30\n"
            full_report += f"  • 📋 <b>팩트 체크:</b> {fact_txt}\n"
            full_report += f"  • 🚀 <b>모멘텀 추적:</b> {momentum_txt}\n"

            # DB(구글 시트)에는 오염되지 않은 순수 원시 데이터(raw)만 저장
            log_data.append([
                today_str, stock_name_original, total_score, rating,
                c_price, round(curr_s['RSI'], 1), str(macd_cross), round(turnover_ratio, 2),
                fund_score, fact_raw, momentum_raw, ""
            ])

        except Exception as e:
            err_str = str(e)
            full_report += f"\n❌ <b>{search_name}</b>: 에러 ({html.escape(err_str)})\n"
            log_data.append([today_str, search_name, "ERROR", "ERROR", "", "", "", "", "", "", "", err_str])

        finally:
            await asyncio.sleep(4)

    await send_message_safe(bot, full_report)

    # [E] 구글 시트 영구 기록 (Trade_Log 헤더 변경 반영)
    if log_data:
        try:
            worksheet = doc.worksheet("Trade_Log")
            first_cell = worksheet.acell('A1').value
            if not first_cell or str(first_cell).strip() == "":
                headers = ["Date", "Stock", "Total_Score", "Rating", "Close", "RSI", "MACD_Cross", "Turnover_Ratio", "Fund_Score", "Fact_Check", "Momentum_Status", "Error_Reason"]
                worksheet.append_row(headers)
            worksheet.append_rows(log_data)
            print("✅ V7.0 구글 시트 영구 기록 완료!")
        except Exception as e:
            await bot.send_message(chat_id=CHAT_ID, text=f"❌ 구글 시트 기록 실패: {html.escape(str(e))}")

if __name__ == "__main__":
    asyncio.run(send_briefing())
