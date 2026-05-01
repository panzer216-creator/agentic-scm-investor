import os
import json
import logging

class BucketFetcher:
    def __init__(self):
        self.universe_path = "data/universe.json"
        self._ensure_universe_exists()

    def _ensure_universe_exists(self):
        """병목 대장주 20선 + 내 포트폴리오(Group E) 4선 템플릿"""
        if not os.path.exists("data"):
            os.makedirs("data")
        
        if not os.path.exists(self.universe_path):
            default_universe = {
                "Group-A (Semicon Bottleneck)": [
                    {"code": "000660", "name": "SK하이닉스", "sector": "HBM/메모리"},
                    {"code": "042700", "name": "한미반도체", "sector": "TC본더"},
                    {"code": "089290", "name": "인텍플러스", "sector": "외관검사"},
                    {"code": "232290", "name": "와이씨", "sector": "검사장비"},
                    {"code": "164060", "name": "필옵틱스", "sector": "유리기판"}
                ],
                "Group-B (Infrastructure/Ship)": [
                    {"code": "329180", "name": "HD현대중공업", "sector": "조선/도크"},
                    {"code": "010140", "name": "삼성중공업", "sector": "LNG선"},
                    {"code": "014620", "name": "성광벤드", "sector": "피팅"},
                    {"code": "023160", "name": "태광", "sector": "피팅"},
                    {"code": "306200", "name": "세아제강", "sector": "강관"}
                ],
                "Group-C (Power/Grid)": [
                    {"code": "267260", "name": "HD현대일렉트릭", "sector": "초고압변압기"},
                    {"code": "010120", "name": "LS일렉트릭", "sector": "전력기기"},
                    {"code": "033100", "name": "제룡전기", "sector": "중소형변압기"},
                    {"code": "298040", "name": "효성중공업", "sector": "변압기"},
                    {"code": "001440", "name": "대한전선", "sector": "전선"}
                ],
                "Group-D (Benchmark & Platform)": [
                    {"code": "005930", "name": "삼성전자", "sector": "벤치마크"},
                    {"code": "000270", "name": "기아", "sector": "밸류업"},
                    {"code": "035420", "name": "NAVER", "sector": "플랫폼"},
                    {"code": "138040", "name": "메리츠금융지주", "sector": "주주환원"},
                    {"code": "105560", "name": "KB금융", "sector": "금리"}
                ],
                "Group-E (My Portfolio)": [
                    {"code": "006400", "name": "삼성SDI", "sector": "2차전지/전고체"},
                    {"code": "131290", "name": "티에스이", "sector": "테스트소켓"},
                    {"code": "263750", "name": "펄어비스", "sector": "게임/신작"},
                    {"code": "082740", "name": "한화엔진", "sector": "선박엔진"}
                ]
            }
            with open(self.universe_path, "w", encoding="utf-8") as f:
                json.dump(default_universe, f, indent=4, ensure_ascii=False)
            logging.info("🌱 신규 유니버스(Group A~E) 생성 완료.")

    def get_dynamic_production_plan(self):
        try:
            with open(self.universe_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"❌ 유니버스 조달 실패: {e}")
            return {}
