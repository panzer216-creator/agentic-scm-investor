import os
import json
import logging
import time
from datetime import datetime

# API Skills & Fetcher
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from skills.bucket_fetcher import BucketFetcher # 추가된 소싱 부품

# AI Agents
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.review_agent import ReviewAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class AgenticSCMEngine:
    def __init__(self, stock_code, stock_name, sector):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.sector = sector
        self.history_path = "data/analysis_history.json"
        self.plan_b_alerts = []
        self.telegram = TelegramApi()

    def _source_data_with_fallback(self) -> dict:
        result = {"price_info": None, "news_list": [], "dart_list": []}
        kis = KISApi()

        if not kis.is_market_open():
            self.plan_b_alerts.append("🔴 휴장일입니다. 마지막 종가 기준으로 공정을 가동합니다.")

        try:
            result["price_info"] = kis.get_stock_data(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ KIS 시세 수급 차질: {e}")

        try:
            result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ 뉴스 수급 차질: {e}")

        try:
            result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ 공시 데이터 수급 차질: {e}")

        return result

    def run_production_line(self, group_id):
        """동적 그룹 ID가 반영된 공정 라인"""
        logging.info(f"🚀 [{group_id}] {self.stock_name}({self.stock_code}) 분석 시작")

        try:
            # 0. 사후 검증 및 피드백 가중치 수령
            agent_weights = ReviewAgent().get_current_weights(self.history_path)

            # 1. Inbound: 데이터 원자재 수집
            raw_data = self._source_data_with_fallback()

            # 2. IQC: 데이터 검수 및 노이즈 제거
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            if "iqc_warning" in parser_result:
                self.plan_b_alerts.append(parser_result["iqc_warning"])

            # 3. Processing: AI 교차 분석
            sdp_payload = parser_result["standard_data_pack"]
            bull_result = BullAgent("Bull", weight=agent_weights['bull']).analyze(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red", weight=agent_weights['red']).analyze(sdp_payload, self.sector)

            # 4. Control: 의사결정 및 자산 배분 통제
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result)
            if "andon_alert" in final_decision:
                self.plan_b_alerts.append(final_decision["andon_alert"])

            # 5. Outbound: 메타데이터 패킹
            final_decision.update({
                'company_name': self.stock_name,
                'group_id': group_id, # 대시보드 A~D 섹션 매핑
                'strategy_tag': f"ETF 동적 수급 ({group_id.upper()})",
                'ui_metrics': self._extract_ui_metrics(raw_data),
                'plan_b_alerts': self.plan_b_alerts,
                'timestamp': datetime.now().isoformat()
            })
            
            # 6. Archive & Delivery
            self._archive_result(final_decision)
            self.telegram.send_report(self.stock_name, final_decision)
            
            logging.info(f"✅ {self.stock_name} 생산 완료")

        except Exception as e:
            logging.error(f"❌ {self.stock_name} 공정 붕괴: {e}")
            self.telegram.send_plain_message(f"🚨 <b>[ANDON]</b> {self.stock_name} 중단\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        p_info = raw_data.get("price_info")
        return {
            "per_pbr": "분석중", "rsi": 50, "peg": 1.0,
            "opm_yoy": "분석중", "order_backlog": p_info.get("dist_from_52w_high", "N/A") if p_info else "N/A",
            "smart_money": "수급 체크중"
        }

    def _archive_result(self, result):
        if not os.path.exists("data"): os.makedirs("data")
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: history = []
        history.append(result)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # [SCM Inbound 공정] ETF 기반 동적 버킷 수급
    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()

    if not production_plan:
        logging.error("❌ [Sourcing Error] ETF 데이터를 가져오지 못했습니다. 공정 중단.")
        exit(1)

    # [SCM 생산 공정] 그룹별 순차 가동
    for group_id, stocks in production_plan.items():
        logging.info(f"🏢 [{group_id}] 섹션 전략 공정 가동")
        for stock in stocks:
            engine = AgenticSCMEngine(
                stock_code=stock["code"],
                stock_name=stock["name"],
                sector=stock["sector"]
            )
            engine.run_production_line(group_id=group_id)
            time.sleep(2) # TPS 보호를 위한 리드타임
            
    logging.info("🏁 오늘의 동적 수급 기반 전체 공정이 완료되었습니다.")
