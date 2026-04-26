import os
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from agents.parser_agent import ParserAgent
import json

def run_test():
    print("🚜 [Step 1] 데이터 공급망 가동 (Skills)...")
    kis = KISApi()
    naver = NaverNewsApi()
    dart = DartApi()
    
    # 삼성전자(005930) 테스트
    stock_code = "005930"
    stock_name = "삼성전자"
    
    # 1. 휴장일 및 시세/수급 조회
    if not kis.is_market_open():
        print("🔴 오늘은 휴장일입니다. (테스트를 위해 시세 조회만 진행)")
    
    price_data = kis.get_stock_data(stock_code)
    news_data = naver.search_stock_news(stock_name)
    dart_data = dart.get_recent_reports(stock_code)
    
    raw_data = {
        "price_info": price_data,
        "news_list": news_data,
        "dart_list": dart_data
    }
    
    print("🧠 [Step 2] Parser Agent 큐레이션 가동...")
    parser = ParserAgent()
    sdp = parser.parse(raw_data, sector="반도체")
    
    print("\n📦 [최종 결과물] 표준 데이터 팩(SDP):")
    print(json.dumps(sdp, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run_test()
