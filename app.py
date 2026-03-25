import os
import pandas as pd
import FinanceDataReader as fdr
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# 1. 환경 설정 및 보안 키 로드
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# 2. 시스템 초기화: KRX 마스터 데이터 로드 (캐싱 및 정규화)
print("⏳ 시스템 초기화: 종목 데이터 정규화 중...")
try:
    KRX_LIST = fdr.StockListing('KRX')
    # 검색 성능을 위해 이름을 모두 대문자로 변환한 열을 추가
    KRX_LIST['Name_Upper'] = KRX_LIST['Name'].str.upper().str.replace(" ", "")
    print(f"✅ {len(KRX_LIST)}개 종목 적재 완료!")
except Exception as e:
    print(f"⚠️ 마스터 데이터 로드 실패: {e}")
    KRX_LIST = pd.DataFrame()

# 3. 데이터 가공 모듈
def get_stock_code(query):
    query = query.strip().upper().replace(" ", "") # 입력값 정규화
    if query.isdigit(): return query
    
    if not KRX_LIST.empty:
        # 정규화된 이름으로 검색
        result = KRX_LIST[KRX_LIST['Name_Upper'] == query]
        if not result.empty:
            return result['Code'].values[0]
    return None

def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['MA20'] = df['Close'].rolling(window=20).mean()
    return df

# 4. 핵심 파이프라인
async def stock_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("💡 사용법: /stock 삼성전자")
        return

    user_query = " ".join(context.args)
    processing_msg = await update.message.reply_text(f"🔍 [{user_query}] 분석 중...")

    try:
        stock_code = get_stock_code(user_query)
        if not stock_code:
            raise ValueError(f"'{user_query}' 종목을 찾을 수 없습니다. 정확한 이름을 입력해 주세요.")

        df = fdr.DataReader(stock_code).tail(60).copy()
        if len(df) < 20: raise ValueError("데이터가 부족합니다.")

        df = calculate_indicators(df)
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        c_price = int(curr['Close'])
        c_percent = ((c_price - int(prev['Close'])) / int(prev['Close'])) * 100
        rsi_val = curr['RSI']
        trend = "상승 추세" if c_price > curr['MA20'] else "하락 추세"

        prompt = f"""
        당신은 금융 분석가입니다. [{user_query}({stock_code})] 데이터를 분석하세요.
        현재가: {c_price:,.0f}원 ({c_percent:+.2f}%) / RSI: {rsi_val:.1f} / 추세: {trend}
        
        지침: 
        1. 위 데이터를 바탕으로 현재 상황을 요약할 것.
        2. 향후 대응 전략을 짧고 명확하게 제안할 것.
        3. 마크다운 기호를 쓰지 말고 평문으로 친절하게 답변할 것.
        """
        
        response = model.generate_content(prompt)
        # 안정성을 위해 parse_mode를 제거하여 특수기호 에러 방지
        await processing_msg.edit_text(f"📈 [{user_query}] 분석 리포트\n\n{response.text}")

    except Exception as e:
        await processing_msg.edit_text(f"⚠️ 알림: {str(e)}")

# 5. 일반 대화 및 가동
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = model.generate_content(update.message.text)
    await update.message.reply_text(response.text)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("stock", stock_analysis))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 최종 보정판 V2.1 가동 완료!")
    app.run_polling()

if __name__ == '__main__':
    main()
