import os
import json
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent

def run_integrated_analysis():
    print("🚜 [Step 1] 데이터 공급망 가동 (Skills)...")
    kis = KISApi()
    naver = NaverNewsApi()
    dart = DartApi()
    
    stock_code = "005930"
    stock_name = "삼성전자"
    
    price_data = kis.get_stock_data(stock_code)
    news_data = naver.search_stock_news(stock_name)
    dart_data = dart.get_recent_reports(stock_code)
    
    raw_data = {
        "price_info": price_data,
        "news_list": news_data,
        "dart_list": dart_data
    }
    
    print("🧠 [Step 2] Parser Agent: 데이터 큐레이션 진행...")
    parser = ParserAgent()
    sdp = parser.parse(raw_data, sector="반도체")
    
    if "error" in sdp:
        print(f"❌ Parser 공정 실패: {sdp['error']}")
        return

    print("📈 [Step 3-1] Bull Agent: 성장 시나리오 분석 중...")
    bull = BullAgent(persona_name="Bull_Analyst")
    bull_result = bull.analyze(sdp, sector="반도체")
    
    print("📉 [Step 3-2] Red Team Agent: 리스크 시나리오 분석 중...")
    red = RedTeamAgent(persona_name="Red_Team")
    red_result = red.analyze(sdp, sector="반도체")
    
    print("\n" + "="*50)
    print("📊 [종합 분석 결과 보고서]")
    print("="*50)
    print(f"\n[Bull의 관점]\n{json.dumps(bull_result, indent=2, ensure_ascii=False)}")
    print(f"\n[Red Team의 관점]\n{json.dumps(red_result, indent=2, ensure_ascii=False)}")
    print("="*50)

if __name__ == "__main__":
    run_integrated_analysis()
