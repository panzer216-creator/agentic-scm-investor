import os
import json
import logging

class BucketFetcher:
    def __init__(self):
        self.universe_path = "data/universe.json"
        self._ensure_universe_exists()

    def _ensure_universe_exists(self):
        """병목 핵심 대장주 중심의 6~8개 확장 유니버스 템플릿"""
        if not os.path.exists("data"):
            os.makedirs("data")
        
        if not os.path.exists(self.universe_path):
            default_universe = {
                "Group-A (Semicon Bottleneck)": [
                    {"code": "000660", "name": "SK하이닉스", "sector": "HBM/메모리"},
                    {"code": "042700", "name": "한미반도체", "sector": "TC본더/독점"},
                    {"code": "089290", "name": "인텍플러스", "sector": "외관검사"},
                    {"code": "232290", "name": "와이씨", "sector": "검사장비"},
                    {"code": "164060", "name": "필옵틱스", "sector": "유리기판"},
                    {"code": "131290", "name": "TSE", "sector": "테스트소켓"},
                    {"code": "039030", "name": "이오테크닉스", "sector": "레이저커팅"},
                    {"code": "003160", "name": "디아이", "sector": "HBM테스트"}
                ],
                "Group-B (Infrastructure/Ship)": [
                    {"code": "329180", "name": "HD현대중공업", "sector": "조선/도크병목"},
                    {"code": "010140", "name": "삼성중공업", "sector": "LNG선/해양"},
                    {"code": "014620", "name": "성광벤드", "sector": "피팅/조선기자재"},
                    {"code": "023160", "name": "태광", "sector": "피팅/조선기자재"},
                    {"code": "033500", "name": "동성화인텍", "sector": "보냉재"},
                    {"code": "306200", "name": "세아제강", "sector": "강관/인프라"}
                ],
                "Group-C (Power/Grid)": [
                    {"code": "267260", "name": "HD현대일렉트릭", "sector": "초고압변압기"},
                    {"code": "010120", "name": "LS일렉트릭", "sector": "전력기기"},
                    {"code": "033100", "name": "제룡전기", "sector": "중소형변압기"},
                    {"code": "298040", "name": "효성중공업", "sector": "변압기/ESS"},
                    {"code": "103590", "name": "일진전기", "sector": "초고압전선"},
                    {"code": "001440", "name": "대한전선", "sector": "해저케이블"}
                ],
                "Group-D (Strategic Reserve)": [
                    {"code": "005930", "name": "삼성전자", "sector": "벤치마크"},
                    {"code": "000270", "name": "기아", "sector": "밸류업/환율"},
                    {"code": "005380", "name": "현대차", "sector": "밸류업"},
                    {"code": "035420", "name": "NAVER", "sector": "플랫폼"},
                    {"code": "138040", "name": "메리츠금융지주", "sector": "주주환원"},
                    {"code": "105560", "name": "KB금융", "sector": "주주환원/금리"}
                ]
            }
            with open(self.universe_path, "w", encoding="utf-8") as f:
                json.dump(default_universe, f, indent=4, ensure_ascii=False)
            logging.info("🌱 신규 확장 투자 유니버스(universe.json) 생성 완료.")

    def get_dynamic_production_plan(self):
        try:
            with open(self.universe_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"❌ 유니버스 조달 실패: {e}")
            return {}
