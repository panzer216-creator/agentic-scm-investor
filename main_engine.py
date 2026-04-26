
import os
import json
import logging
from datetime import datetime

# 공정 부품 임포트
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent

# 로깅 설정 (공정 로그 기록)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AgenticSCMEngine:
    def __init__(self):
        self.stock_code = "005930" # 삼성전자 (향후 리스트 관리 가능)
        self.stock_name = "삼성전자"
        self.sector = "반도체"

    def run_production_line(self):
        logging.info(f"🚀 {self.stock_name} 분석 공정 시작")
        
        try:
            # [Step 1] 원재료 수급 (Data Sourcing)
            raw_data = self._source_raw_data()
            
            # [Step 2] 데이터 정제 (Parsing & Curation)
            sdp = ParserAgent().parse(raw_data, self.sector)
            if "error" in sdp: raise Exception(f"Parser 공정 결함: {sdp['error']}")

            # [Step 3] 다각도 분석 (Dialectical Analysis)
            bull_result = BullAgent("Bull_Analyst").analyze(sdp, self.sector)
            red_result = RedTeamAgent("Red_Team").analyze(sdp, self.sector)

            # [Step 4] 최종 의사결정 (Orchestration)
            final_decision = OrchestratorAgent().decide(sdp, bull_result, red_result)

            # [Step 5] 산출물 보관 및 배송 (Archiving & Delivery)
            self._archive_result(final_decision)
            TelegramApi().send_report(self.stock_name, final_decision)
            
            logging.info("✅ 전체 분석 공정 완료 및 리포트 배송 성공")

        except Exception as e:
            logging.error(f"❌ 공정 중단 발생: {str(e)}")
            # 비상 알림 발송 로직 추가 가능

    def _source_raw_data(self):
        logging.info("📦 원재료 수급 중...")
        return {
            "price_info": KISApi().get_stock_data(self.stock_code),
            "news_list": NaverNewsApi().search_stock_news(self.stock_name),
            "dart_list": DartApi().get_recent_reports(self.stock_code)
        }

    def _archive_result(self, result):
        """분석 결과를 데이터베이스(JSON)에 기록하여 피드백 루프의 자산으로 활용"""
        path = "data/analysis_history.json"
        history = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        
        result["timestamp"] = datetime.now().isoformat()
        history.append(result)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, indent=2, ensure_ascii=False) # 최근 100건 보존

if __name__ == "__main__":
    engine = AgenticSCMEngine()
    engine.run_production_line()
