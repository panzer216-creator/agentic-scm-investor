import os
import requests
from datetime import datetime, timedelta

class DartApi:
    def __init__(self):
        # GHA Secrets에서 DART API 키 로드
        self.api_key = os.getenv("DART_API_KEY")
        self.base_url = "https://opendart.fss.or.kr/api/list.json"

    def get_recent_reports(self, stock_code, days=90):
        """Mission 4: 최근 90일간의 주요 공시 목록 추출"""
        # 시작 날짜 계산 (현재로부터 90일 전)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        params = {
            "crtfc_key": self.api_key,
            "corp_code": stock_code, # 종목코드로 직접 검색 가능
            "bgn_de": start_date,
            "end_de": end_date,
            "page_count": 10
        }

        try:
            response = requests.get(self.base_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "000": # 정상 응답 코드
                    reports = []
                    for item in data.get("list", []):
                        reports.append({
                            "date": item["report_nm"][:10].replace(".","-"), # 가독성 정제
                            "title": item["report_nm"],
                            "receipt_no": item["rcept_no"], # 상세 조회용 키
                            "corp_name": item["corp_name"]
                        })
                    return reports
                elif data.get("status") == "013": # 데이터 없음
                    return []
                else:
                    print(f"❌ DART API 에러 메시지: {data.get('message')}")
                    return []
            return []
        except Exception as e:
            print(f"⚠️ DART 수집 중 예외 발생: {e}")
            return []

# --- [단독 검증 모듈: DART API 테스트] ---
if __name__ == "__main__":
    print("🚀 DART 공시 목록 수집 테스트 시작...")
    
    dart = DartApi()
    # 삼성전자(005930) 테스트
    test_code = "005930"
    results = dart.get_recent_reports(test_code)

    if results:
        print(f"✅ 최근 90일간 공시 {len(results)}건 확보 성공\n")
        for i, report in enumerate(results, 1):
            print(f"[{i}] {report['title']} (접수번호: {report['receipt_no']})")
    else:
        print("❌ 공시 데이터를 가져오지 못했습니다. API 키 또는 종목코드를 확인하세요.")

