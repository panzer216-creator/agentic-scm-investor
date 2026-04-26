import os
import json
import logging

class BucketFetcher:
    def __init__(self):
        # 종목 리스트를 코드가 아닌 외부 설정 파일로 분리 (동적 조달)
        self.universe_path = "data/universe.json"
        self._ensure_universe_exists()

    def _ensure_universe_exists(self):
        """유니버스 파일이 없으면 SCM 병목 중심의 기본 템플릿을 자동 생성합니다."""
        if not os.path.exists("data"):
            os.makedirs("data")
        
        if not os.path.exists(self.universe_path):
            default_universe = {
                "Group-A (Semicon Bottleneck)": [
                    {"code": "000660", "name": "SK하이닉스", "sector": "HBM/반도체"},
                    {"code": "042700", "name": "한미반도체", "sector": "TC본더/반도체"},
                    {"code": "089290", "name": "인텍플러스", "sector": "외관검사/반도체"},
                    {"code": "232290", "name": "와이씨", "sector": "검사장비/반도체"},
                    {"code": "164060", "name": "필옵틱스", "sector": "유리기판/반도체"}
                ],
                "Group-B (Infrastructure/Ship)": [
                    {"code": "010620", "name": "HD현대중공업", "sector": "조선/물류병목"},
                    {"code": "267260", "name": "HD현대일렉트릭", "sector": "변압기/전력병목"},
                    {"code": "010120", "name": "LS", "sector": "전력인프라"}
                ],
                "Group-C (Value-Up & Energy)": [
                    {"code": "000270", "name": "기아", "sector": "밸류업/자동차"},
                    {"code": "000880", "name": "한화", "sector": "방산/에너지"}
                ],
                "Group-D (Strategic Reserve)": [
                    {"code": "005930", "name": "삼성전자", "sector": "벤치마크/반도체"},
                    {"code": "035420", "name": "NAVER", "sector": "AI인프라"}
                ]
            }
            with open(self.universe_path, "w", encoding="utf-8") as f:
                json.dump(default_universe, f, indent=4, ensure_ascii=False)
            logging.info("🌱 신규 투자 유니버스(universe.json) 템플릿이 생성되었습니다.")

    def get_dynamic_production_plan(self):
        """외부 파일에서 동적으로 타겟 리스트를 조달합니다."""
        try:
            with open(self.universe_path, "r", encoding="utf-8") as f:
                production_plan = json.load(f)
            
            total_stocks = sum(len(stocks) for stocks in production_plan.values())
            logging.info(f"📋 외부 유니버스에서 총 {total_stocks}개 종목 조달 완료")
            return production_plan
            
        except Exception as e:
            logging.error(f"❌ 유니버스 조달 실패: {e}")
            return {}
