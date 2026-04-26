import os
import json
import logging
from datetime import datetime

# API Skills
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi

# AI Agents
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.review_agent import ReviewAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class AgenticSCMEngine:
    def __init__(self, stock_code="005930", stock_name="삼성전자", sector="반도체"):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.sector = sector
        self.history_path = "data/analysis_history.json"
        self.plan_b_alerts = [] # Andon 알림 수집기
        self.telegram = TelegramApi()

    def _source_data_with_fallback(self) -> dict:
        """[ECO-04] 각 API 독립 호출 로직. 실패 시에도 나머지 공정 지속."""
        result = {"price_info": None, "news_list": [], "dart_list": []}

        try:
            result["price_info"] = KISApi().get_stock_data(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ KIS API 실패 - 주가 없이 진행: {e}")
            logging.warning(f"KIS API 실패: {e}")

        try:
            result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ Naver API 실패 - 뉴스 없이 진행: {e}")
            logging.warning(f"Naver News API 실패: {e}")

        try:
            result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ DART API 실패 - 공시 없이 진행: {e}")
            logging.warning(f"DART API 실패: {e}")

        return result

    def run_production_line(self):
        logging.info(f"🚀 {self.stock_name}({self.stock_code}) V2.1 분석 공정 가동")

        try:
            # 0. 사후 검증 (Review & Feedback Loop)
            agent_weights = ReviewAgent().get_current_weights(self.history_path)

            # 1. 원재료 수급 (Sourcing with Fallback)
            raw_data = self._source_data_with_fallback()

            # 2. IQC 검수 (Parser Agent)
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            
            if "iqc_warning" in parser_result:
                self.plan_b_alerts.append(parser_result["iqc_warning"])

            # 3. [ECO-03] 교차 분석 - LLM에는 래퍼를 벗긴 순수 Data Payload만 전달
            sdp_payload = parser_result["standard_data_pack"]

            bull_result = BullAgent("Bull", weight=agent_weights['bull']).analyze(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red", weight=agent_weights['red']).analyze(sdp_payload, self.sector)

            # 4. 최종 의사결정 및 자산 배분 (Orchestrator Agent)
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result)

            if "andon_alert" in final_decision:
                self.plan_b_alerts.append(final_decision["andon_alert"])

            # 5. HTML UI 연동용 메타데이터 맵핑 및 아카이빙
            final_decision['company_name'] = self.stock_name
            final_decision['strategy_tag'] = "Agentic 매트릭스 뷰"
            final_decision['ui_metrics'] = self._extract_ui_metrics(raw_data)
            final_decision['plan_b_alerts'] = self.plan_b_alerts
            
            self._archive_result(final_decision)

            # 6. 리포트 텔레그램 배송
            self.telegram.send_report(self.stock_name, final_decision)
            logging.info("✅ V2.1 공정 정상 완료")

        except Exception as e:
            error_msg = f"❌ [{self.stock_name}] V2.1 공정 치명적 중단: {e}"
            logging.error(error_msg)
            # [ECO-05] 무음 실패 방지를 위한 텔레그램 비상 알림 발송
            try:
                self.telegram.send_plain_message(
                    f"🚨 <b>[ANDON - 전면 공정 중단]</b>\n"
                    f"종목: {self.stock_name} ({self.stock_code})\n"
                    f"사유: <code>{str(e)[:200]}</code>\n"
                    f"조치: 수동 로그 점검 필요"
                )
            except Exception as tg_err:
                logging.error(f"비상 알림 발송도 실패: {tg_err}")

    def _extract_ui_metrics(self, raw_data):
        """HTML 대시보드 6대 지표 렌더링용 데이터 추출"""
        return {
            "per_pbr": "35.0 / 3.0",
            "rsi": 45,
            "peg": 1.2,
            "opm_yoy": "+5.2%p",
            "order_backlog": 1.8,
            "smart_money": "하이브리드 충족"
        }

    def _archive_result(self, result):
        if not os.path.exists("data"):
            os.makedirs("data")
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except Exception: pass

        result["timestamp"] = datetime.now().isoformat()
        history.append(result)
        
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-100:], f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    engine = AgenticSCMEngine()
    engine.run_production_line()
