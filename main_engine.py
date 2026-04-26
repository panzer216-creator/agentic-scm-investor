import os
import json
import logging
from datetime import datetime

# [공정 부품 임포트]
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent

# [SCM 로깅 설정] 공정의 모든 발자국을 기록합니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class AgenticSCMEngine:
    def __init__(self, stock_code="005930", stock_name="삼성전자", sector="반도체"):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.sector = sector
        self.history_path = "data/analysis_history.json"

    def run_production_line(self):
        logging.info(f"🚀 {self.stock_name}({self.stock_code}) 분석 공정 가동 시작")
        
        try:
            # 1. 원재료 수급 (Sourcing)
            raw_data = self._source_data()
            
            # 2. 데이터 정제 (Parsing)
            sdp = ParserAgent().parse(raw_data, self.sector)
            if "error" in sdp: raise Exception(f"Parser 결함 발생: {sdp['error']}")

            # 3. 관점 분석 (Dialectical Analysis)
            bull_result = BullAgent("Bull_Analyst").analyze(sdp, self.sector)
            red_result = RedTeamAgent("Red_Team").analyze(sdp, self.sector)

            # 4. 최종 의사결정 (Orchestration)
            final_decision = OrchestratorAgent().decide(sdp, bull_result, red_result)

            # 5. 데이터 아카이빙 및 배송 (Archiving & Delivery)
            self._archive_result(final_decision)
            TelegramApi().send_report(self.stock_name, final_decision)
            
            logging.info("✅ 리포트 배송 완료. 전체 공정 정상 종료.")

        except Exception as e:
            error_msg = f"❌ 공정 중단 발생: {str(e)}"
            logging.error(error_msg)
            # 비상시 텔레그램으로 장애 알림을 보낼 수 있는 확장성을 열어둡니다.

    def _source_data(self):
        logging.info("📦 원재료(KIS/Naver/DART) 수집 중...")
        return {
            "price_info": KISApi().get_stock_data(self.stock_code),
            "news_list": NaverNewsApi().search_stock_news(self.stock_name),
            "dart_list": DartApi().get_recent_reports(self.stock_code)
        }

    def _archive_result(self, result):
        """분석 이력을 저장하여 향후 '통계적 피드백 루프'의 기초 자산으로 활용"""
        if not os.path.exists("data"): os.makedirs("data")
        
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: history = []
        
        # 메타 데이터 보강
        result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["stock_name"] = self.stock_name
        history.append(result)
        
        # 최근 100건의 분석 결과만 보관 (저장 공간 최적화)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    engine = AgenticSCMEngine()
    engine.run_production_line()
