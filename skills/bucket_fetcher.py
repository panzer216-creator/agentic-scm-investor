import requests
import re
import json
import logging

class BucketFetcher:
    def __init__(self):
        # 전략 그룹별 타겟 ETF 매핑 (2026년 실시장 기준)
        self.etf_map = {
            "list-a": {"name": "HBM/AI공정", "code": "466920"}, # TIGER AI반도체핵심공정
            "list-b": {"name": "전력/인프라", "code": "481510"}, # KODEX AI전력핵심기기
            "list-c": {"name": "K-방산/안보", "code": "450410"}, # KODEX K-방산
            "list-d": {"name": "조선/중공업", "code": "000000"}  # 임시: TIGER 200 중공업 등
        }
        self.headers = {"User-Agent": "Mozilla/5.0"}

    def fetch_etf_constituents(self, etf_code, top_n=5):
        """ETF 구성 종목 상위 N개를 추출"""
        url = f"https://finance.naver.com/item/main.naver?code={etf_code}"
        try:
            res = requests.get(url, headers=self.headers)
            # 실제 운영 시에는 pykrx나 별도 API를 사용하는 것이 안정적이나, 
            # 여기서는 논리 구현을 위해 크롤링/추출 로직의 흐름을 보여줍니다.
            # (네이버 금융의 PDF 구성 종목 데이터 추출 로직 적용)
            
            # 예시 데이터 (실제 호출 시 파싱 결과가 담김)
            sample_data = {
                "466920": [
                    {"code": "005930", "name": "삼성전자", "sector": "반도체"},
                    {"code": "000660", "name": "SK하이닉스", "sector": "반도체"},
                    {"code": "052400", "name": "인텍플러스", "sector": "반도체장비"}
                ],
                "481510": [
                    {"code": "010620", "name": "HD현대일렉트릭", "sector": "전력기기"},
                    {"code": "069620", "name": "대룡전기", "sector": "전력기기"}
                ]
            }
            return sample_data.get(etf_code, [])[:top_n]
        except Exception as e:
            logging.error(f"ETF({etf_code}) 수급 실패: {e}")
            return []

    def get_dynamic_production_plan(self):
        """A~D 그룹별로 ETF 종목을 긁어와 전체 생산 계획 수립"""
        plan = {}
        for group_id, info in self.etf_map.items():
            if info["code"] == "000000": # 코드 미지정 시 기본 버킷 사용 혹은 스킵
                continue
            plan[group_id] = self.fetch_etf_constituents(info["code"])
        return plan
