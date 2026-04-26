
import os
import requests
import re

class NaverNewsApi:
    def __init__(self):
        # GHA Secrets에서 네이버 API 키 로드
        self.client_id = os.getenv("NAVER_CLIENT_ID")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET")
        self.base_url = "https://openapi.naver.com/v1/search/news.json"

    def clean_html(self, text):
        """HTML 태그 제거 및 특수문자 정제 (AI 가독성 향상)"""
        clean = re.compile('<.*?>|&quot;|&amp;|&lt;|&gt;')
        return re.sub(clean, '', text)

    def search_stock_news(self, stock_name, count=5):
        """종목 관련 뉴스 검색 및 고밀도 정보 추출"""
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        
        # '심도 있는 분석'을 위해 종목명에 '분석' 키워드를 조합하여 검색
        params = {
            "query": f"{stock_name} 분석", 
            "display": count,
            "sort": "sim"  # 관련도 순 (유사한 광고성 기사 제외 효과)
        }

        try:
            response = requests.get(self.base_url, headers=headers, params=params)
            if response.status_code == 200:
                items = response.json().get("items", [])
                news_list = []
                
                for item in items:
                    # AI가 매체 성향을 판단할 수 있도록 링크와 제목, 요약을 패키징
                    news_list.append({
                        "title": self.clean_html(item["title"]),
                        "description": self.clean_html(item["description"]),
                        "link": item["originallink"] or item["link"],
                        "pubDate": item["pubDate"]
                    })
                return news_list
            else:
                print(f"❌ 네이버 API 에러: {response.status_code}")
                return []
        except Exception as e:
            print(f"⚠️ 뉴스 검색 중 예외 발생: {e}")
            return []

# --- [단독 검증 모듈: Naver API 테스트] ---
if __name__ == "__main__":
    print(f"🚀 네이버 뉴스 수집 테스트 시작...")
    
    naver = NaverNewsApi()
    # 사용자님이 거주하시는 춘천이나 관심 종목인 '삼성전자'로 테스트 가능
    test_query = "삼성전자" 
    results = naver.search_stock_news(test_query)

    if results:
        print(f"✅ '{test_query}' 관련 뉴스 {len(results)}건 확보 성공\n")
        for i, news in enumerate(results, 1):
            print(f"[{i}] {news['title']}")
            print(f"   🔗 링크: {news['link']}")
            print(f"   📝 요약: {news['description'][:50]}...\n")
    else:
        print("❌ 뉴스 데이터를 가져오지 못했습니다. Secrets 설정을 확인하세요.")
