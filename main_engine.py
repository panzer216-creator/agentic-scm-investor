import os
import json
import re
import logging
import time
from datetime import datetime

# [1] API Skills (공급망 원재료 조달부)
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from skills.bucket_fetcher import BucketFetcher

# [2] 하네스 공정이 적용된 에이전트 레이어
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.review_agent import ReviewAgent

# 로깅 설정 (공정 모니터링)
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
        """[공정 1] 데이터 원재료 수급 및 규격 검수 (IQC)"""
        result = {"price_info": {}, "news_list": [], "dart_list": []}
        kis = KISApi()

        try:
            p_data = kis.get_stock_data(self.stock_code)
            # [타입 하네스 강화 1] 비정상 규격 데이터 방어
            if isinstance(p_data, dict):
                result["price_info"] = p_data
            elif isinstance(p_data, list) and len(p_data) > 0 and isinstance(p_data[0], dict):
                result["price_info"] = p_data[0]
            else:
                result["price_info"] = {} 
        except Exception as e:
            logging.warning(f"⚠️ {self.stock_name} 시세 수급 차질: {e}")

        try: result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except: pass

        try: result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except: pass

        return result

    def run_production_line(self, group_id, trigger_reason, current_report_id):
        """[공정 2] 하네스 기반 통합 분석 및 완제품 패킹"""
        logging.info(f"🚀 [{group_id}] {self.stock_name} 생산 시작 (사유: {trigger_reason})")

        try:
            # 1. 원재료 수집
            raw_data = self._source_raw_materials()

            # 2. 데이터 정제 (ParserAgent)
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            
            # [타입 하네스 강화 2] Parser 반환값 강제 파싱 (String 에러 원천 차단)
            if isinstance(parser_result, str):
                try:
                    clean_str = re.sub(r'```json|```', '', parser_result).strip()
                    parser_result = json.loads(clean_str)
                except:
                    parser_result = {}
            if not isinstance(parser_result, dict):
                parser_result = {}

            sdp_payload = parser_result.get("standard_data_pack", {})

            # 3. 모델 분석 가동
            bull_result = BullAgent("Bull").analyze(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red").analyze(sdp_payload, self.sector)

            # 4. 의사결정 조립 (Orchestration)
            p_info = raw_data.get("price_info", {})
            curr_price = p_info.get("current_price", 0) if isinstance(p_info, dict) else 0
            
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result, self.stock_code, curr_price)

            # 5. [하네스 규격 강제] 완제품 패킹
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
                'reasoning': final_decision.get('reasoning', ["분석 리포트 생성 중"]),
                'ui_metrics': self._extract_ui_metrics(raw_data),
                'produced_by': final_decision.get('produced_by', 'Unknown'),
                'timestamp': datetime.now().isoformat()
            }

            if not isinstance(output['reasoning'], list):
                output['reasoning'] = [str(output['reasoning'])]

            # 6. 창고 입고 및 고객 배송
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
            
            logging.info(f"✅ {self.stock_name} 공정 완료 (Tier: {output['produced_by']})")

        except Exception as e:
            # [블랙박스 해체] 에러 발생 시 상세 역추적(Traceback) 일지 출력
            logging.exception(f"❌ {self.stock_name} 라인 중단: {e}")
            self.telegram.send_plain_message(f"🚨 <b>[ANDON]</b> {self.stock_name} 공정 붕괴\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        p_info = raw_data.get("price_info", {})
        if not isinstance(p_info, dict): p_info = {}
        curr_price = p_info.get("current_price", 0)
        return {
            "per_pbr": f"{p_info.get('per', 'N/A')} / {p_info.get('pbr', 'N/A')}",
            "rsi": 50,
            "peg": 1.0,
            "opm_yoy": "분석중",
            "order_backlog": p_info.get("dist_from_52w_high", "N/A"),
            "smart_money": "수급 분석중",
            "last_analyzed_price": curr_price
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
    """[SCM 지능형 제어] 공시 및 주가 변동성 트리거"""
    target_history = [h for h in history_list if h.get('stock_code') == stock_code]
    if not target_history: return True, "신규 종목 초기화", "INITIAL"

    last_record = target_history[-1]
    current_report_id = DartApi().get_latest_report_id(stock_code)
    
    if current_report_id != last_record.get("data_fingerprint"):
        return True, "신규 공시/데이터 감지", current_report_id

    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    curr_price = current_price_data.get("current_price", 0) if isinstance(current_price_data, dict) else 0
    
    if last_price > 0 and curr_price > 0:
        change_rate = abs((curr_price - last_price) / last_price) * 100
        if change_rate >= 5.0:
            return True, f"주가 변동성 임계치 초과 ({change_rate:.1f}%)", current_report_id

    return False, "변동 사항 없음 (공정 스킵)", current_report_id

if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Investment Engine v2.2 가동 시작")
    
    # [사전 공정 준비] 물리적 창고 부지 선확보 (Git 추적 유실 방지)
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "w", encoding="utf-8") as f:
            json.dump([], f)

    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()
    
    # [조달망 방어] 조달 리스트가 비어있을 경우 무음 붕괴 차단
    if not production_plan:
        logging.error("🚨 조달 실패: 분석할 종목 리스트(Production Plan)가 비어 있습니다.")
        exit(1)

    history = []
    if os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []

    kis = KISApi()
    for group_id, stocks in production_plan.items():
        for stock in stocks:
            try:
                curr_price_info = kis.get_stock_data(stock["code"])
                run_flag, reason, report_id = should_run_analysis(stock["code"], curr_price_info, history)
                
                if run_flag:
                    engine = AgenticSCMEngine(stock["code"], stock["name"], stock["sector"])
                    engine.run_production_line(group_id, reason, report_id)
                    time.sleep(2)
                else:
                    logging.info(f"☕ {stock['name']}: {reason}")
                    
            except Exception as e:
                # [블랙박스 해체] 최상위 루프에서도 상세 추적 일지 활성화
                logging.exception(f"⚠️ {stock['name']} 공정 준비 중 오류: {e}")

    logging.info("🏁 오늘의 생산 공정이 종료되었습니다.")
