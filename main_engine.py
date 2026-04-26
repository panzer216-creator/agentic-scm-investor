import os
import json
import logging
import time
from datetime import datetime

# [1] API Skills
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from skills.bucket_fetcher import BucketFetcher

# [2] 에이전트 레이어
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.review_agent import ReviewAgent

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class AgenticSCMEngine:
    def __init__(self, stock_code, stock_name, sector):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.sector = sector
        self.history_path = "data/analysis_history.json"
        self.telegram = TelegramApi()

    def _source_raw_materials(self) -> dict:
        """[공정 1] 원재료 수급 및 이중 타입 절연"""
        result = {"price_info": {}, "news_list": [], "dart_list": []}
        kis = KISApi()

        try:
            p_data = kis.get_stock_data(self.stock_code)
            if isinstance(p_data, dict): result["price_info"] = p_data
            elif isinstance(p_data, list) and p_data: result["price_info"] = p_data[0]
        except Exception as e:
            logging.warning(f"⚠️ {self.stock_name} 시세 수급 차질: {e}")

        try: result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except: pass

        try: result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except: pass

        return result

    def run_production_line(self, group_id, trigger_reason, current_report_id):
        """[공정 2] 통합 분석 및 안전 규격 배송"""
        logging.info(f"🚀 [{group_id}] {self.stock_name} 가동 (사유: {trigger_reason})")

        try:
            # 1. 원재료 수집 및 전처리
            raw_data = self._source_raw_materials()
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            sdp_payload = parser_result.get("standard_data_pack", {})

            # 2. 하네스 기반 분석 (Self-Correction Loop 포함)
            bull_result = BullAgent("Bull").analyze(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red").analyze(sdp_payload, self.sector)

            # 3. 의사결정 조립
            p_info = raw_data.get("price_info", {})
            curr_price = p_info.get("current_price", 0) if isinstance(p_info, dict) else 0
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result, self.stock_code, curr_price)

            # 4. [배송 하네스] 텔레그램 규격 검수 (4,096자 제한 대응)
            reasoning = final_decision.get('reasoning', ["분석 결과 생성 중"])
            if not isinstance(reasoning, list): reasoning = [str(reasoning)]
            
            full_text = "\n".join(reasoning)
            if len(full_text) > 3500:
                full_text = full_text[:3500] + "\n...[데이터 과다로 인한 중략]"
                reasoning = [full_text]

            output = {
                'stock_code': self.stock_code,
                'company_name': self.stock_name,
                'group_id': group_id,
                'data_fingerprint': current_report_id,
                'conclusion': {
                    'Action': final_decision.get('Action', '관망'),
                    'Gauge_Bar': int(final_decision.get('Gauge_Bar', 50)),
                    'Max_Weight': final_decision.get('Max_Weight', '0%')
                },
                'reasoning': reasoning,
                'ui_metrics': self._extract_ui_metrics(raw_data),
                'produced_by': final_decision.get('produced_by', 'Unknown'),
                'timestamp': datetime.now().isoformat()
            }

            # 5. 창고 입고 및 배송
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
            
            logging.info(f"✅ {self.stock_name} 공정 완료")

        except Exception as e:
            logging.exception(f"❌ {self.stock_name} 라인 중단: {e}")
            self.telegram.send_plain_message(f"🚨 [ANDON] {self.stock_name} 중단\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        p_info = raw_data.get("price_info", {})
        if not isinstance(p_info, dict): p_info = {}
        return {
            "per_pbr": f"{p_info.get('per', 'N/A')} / {p_info.get('pbr', 'N/A')}",
            "rsi": 50,
            "peg": 1.0,
            "order_backlog": p_info.get("dist_from_52w_high", "N/A"),
            "last_analyzed_price": p_info.get("current_price", 0)
        }

    def _archive_result(self, result):
        if not os.path.exists("data"): os.makedirs("data")
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: history = []
        
        history = [h for h in history if h.get('stock_code') != result['stock_code']]
        history.append(result)
        
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)

def should_run_analysis(stock_code, current_price_data, history_list):
    """지능형 수급 제어: 변동 감지 시에만 분석 가동"""
    target_history = [h for h in history_list if h.get('stock_code') == stock_code]
    if not target_history: return True, "신규 종목 진입", "INITIAL"

    last_record = target_history[-1]
    current_report_id = DartApi().get_latest_report_id(stock_code)
    
    if current_report_id != last_record.get("data_fingerprint"):
        return True, "신규 공시 감지", current_report_id

    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    curr_price = current_price_data.get("current_price", 0) if isinstance(current_price_data, dict) else 0
    
    if last_price > 0 and curr_price > 0:
        if abs((curr_price - last_price) / last_price) * 100 >= 5.0:
            return True, "주가 급변 감지", current_report_id

    return False, "변동 사항 없음", current_report_id

if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Investment Engine v2.2 가동")
    
    # 기초 인프라 구축
    if not os.path.exists("data"): os.makedirs("data")
    if not os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "w", encoding="utf-8") as f: json.dump([], f)

    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()
    
    if not production_plan:
        logging.error("🚨 조달 리스트 공백")
        exit(1)

    with open("data/analysis_history.json", "r", encoding="utf-8") as f:
        history = json.load(f)

    kis = KISApi()
    for group_id, stocks in production_plan.items():
        for stock in stocks:
            try:
                curr_price_info = kis.get_stock_data(stock["code"])
                run_flag, reason, report_id = should_run_analysis(stock["code"], curr_price_info, history)
                
                if run_flag:
                    engine = AgenticSCMEngine(stock["code"], stock["name"], stock["sector"])
                    engine.run_production_line(group_id, reason, report_id)
                    time.sleep(1) # 유료 API 사용으로 휴지기 단축
                else:
                    logging.info(f"☕ {stock['name']}: 스킵 ({reason})")
            except Exception as e:
                logging.exception(f"⚠️ {stock['name']} 공정 준비 오류: {e}")
