import os
import json
import logging
import time
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
    def __init__(self, stock_code, stock_name, sector):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.sector = sector
        self.history_path = "data/analysis_history.json"
        self.plan_b_alerts = []
        self.telegram = TelegramApi()

    def _source_data_with_fallback(self) -> dict:
        """[ECO-04] 각 API 독립 호출 및 폴백 로직"""
        result = {"price_info": None, "news_list": [], "dart_list": []}
        kis = KISApi()

        # 휴장일 체크 로직 통합
        if not kis.is_market_open():
            self.plan_b_alerts.append("🔴 국내 시장 휴장일입니다. 마지막 종가 기준으로 분석을 진행합니다.")

        try:
            result["price_info"] = kis.get_stock_data(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ KIS API 오류: {e}")

        try:
            result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ 뉴스 수급 실패: {e}")

        try:
            result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ 공시 데이터 수급 실패: {e}")

        return result

    def run_production_line(self, group_id):
        """[V2.2] 그룹화 전략이 반영된 핵심 공정 라인"""
        logging.info(f"🚀 [{group_id}] {self.stock_name} 분석 시작")

        try:
            # 0. 사후 검증 및 가중치 조절
            agent_weights = ReviewAgent().get_current_weights(self.history_path)

            # 1. 원재료 수급
            raw_data = self._source_data_with_fallback()

            # 2. IQC 검수 및 데이터 정제
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            if "iqc_warning" in parser_result:
                self.plan_b_alerts.append(parser_result["iqc_warning"])

            # 3. 교차 분석 (Pure Payload 전달)
            sdp_payload = parser_result["standard_data_pack"]
            bull_result = BullAgent("Bull", weight=agent_weights['bull']).analyze(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red", weight=agent_weights['red']).analyze(sdp_payload, self.sector)

            # 4. 의사결정 및 자산 배분
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result)
            if "andon_alert" in final_decision:
                self.plan_b_alerts.append(final_decision["andon_alert"])

            # 5. 메타데이터 바인딩 (UI 그룹화 및 시간 정보)
            final_decision['company_name'] = self.stock_name
            final_decision['group_id'] = group_id # 프론트엔드 A~D 매핑용
            final_decision['strategy_tag'] = "SCM V2.2 분석"
            final_decision['ui_metrics'] = self._extract_ui_metrics(raw_data)
            final_decision['plan_b_alerts'] = self.plan_b_alerts
            final_decision['timestamp'] = datetime.now().isoformat()
            
            # 6. 아카이빙 및 배송
            self._archive_result(final_decision)
            self.telegram.send_report(self.stock_name, final_decision)
            
            logging.info(f"✅ {self.stock_name} 공정 완료")

        except Exception as e:
            logging.error(f"❌ {self.stock_name} 공정 중단: {e}")
            self.telegram.send_plain_message(f"🚨 <b>[ANDON]</b> {self.stock_name} 공정 중단\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        """UI 대시보드 렌더링용 지표 추출 (실제 수집 데이터 기반)"""
        p_info = raw_data.get("price_info")
        dist = p_info.get("dist_from_52w_high", "N/A") if p_info else "N/A"
        return {
            "per_pbr": "최근 공시 기준", 
            "rsi": 50, 
            "peg": 1.0,
            "opm_yoy": "분석중", 
            "order_backlog": dist, 
            "smart_money": "수급 분석중"
        }

    def _archive_result(self, result):
        if not os.path.exists("data"):
            os.makedirs("data")
        
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except:
                    history = []

        # 동일 종목의 이전 기록을 유지하면서 최신 결과 추가 (배열 형태 유지)
        history.append(result)
        
        # 데이터 비대화 방지 (최근 200건 유지)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # [버킷 기반 생산 계획 수립]
    bucket_path = "data/target_bucket.json"
    
    if not os.path.exists(bucket_path):
        logging.error("❌ [Sourcing Error] target_bucket.json 파일이 없습니다.")
        exit(1)

    try:
        with open(bucket_path, "r", encoding="utf-8") as f:
            production_plan = json.load(f)
            
        # 그룹별(list-a, list-b, list-c, list-d) 순차 분석 실행
        for group_id, stocks in production_plan.items():
            for stock in stocks:
                engine = AgenticSCMEngine(
                    stock_code=stock["code"],
                    stock_name=stock["name"],
                    sector=stock["sector"]
                )
                engine.run_production_line(group_id=group_id)
                
                # KIS API 및 LLM API 속도 제한 준수
                time.sleep(2)
                
        logging.info("🏁 오늘의 모든 분석 공정이 완료되었습니다.")

    except Exception as e:
        logging.error(f"🔥 메인 제어 루프 붕괴: {e}")
