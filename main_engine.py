import os
import json
import logging
import time
from datetime import datetime

# [1] API Skills & Sourcing 부품
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from skills.bucket_fetcher import BucketFetcher

# [2] 하네스 엔지니어링이 적용된 에이전트 레이어
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.review_agent import ReviewAgent

# 로깅 설정
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
        self.plan_b_alerts = []

    def _source_raw_materials(self) -> dict:
        """[공정 1] 데이터 원재료 수급 (Defensive Sourcing)"""
        result = {"price_info": {}, "news_list": [], "dart_list": []}
        kis = KISApi()

        try:
            # 시세 수급 및 타입 검수 (리스트 에러 방지 하네스)
            p_data = kis.get_stock_data(self.stock_code)
            result["price_info"] = p_data if isinstance(p_data, dict) else (p_data[0] if p_data else {})
        except Exception as e:
            self.plan_b_alerts.append(f"⚠️ KIS API 수급 차질")

        try:
            result["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
        except: pass

        try:
            result["dart_list"] = DartApi().get_recent_reports(self.stock_code)
        except: pass

        return result

    def run_production_line(self, group_id, trigger_reason, current_report_id):
        """[공정 2] 핵심 분석 및 하네스 기반 데이터 패킹"""
        logging.info(f"🚀 [{group_id}] {self.stock_name} 생산 시작 (사유: {trigger_reason})")

        try:
            # 1. 원재료 수집
            raw_data = self._source_raw_materials()

            # 2. IQC (데이터 정제 및 스키마 검수)
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            sdp_payload = parser_result.get("standard_data_pack", {})

            # 3. 3-Tier 하네스 분석 (Flash -> 3.1 Pro -> 2.5 Pro)
            # 각 에이전트 내부에 하네스 로직이 탑재되어 있다고 가정
            bull_result = BullAgent("Bull").analyze_with_harness(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red").analyze_with_harness(sdp_payload, self.sector)

            # 4. 의사결정 (Orchestration)
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result)

            # 5. [하네스 규격 강제] 대시보드 및 텔레그램용 완제품 포장
            output = {
                'stock_code': self.stock_code,
                'company_name': self.stock_name,
                'group_id': group_id,
                'data_fingerprint': current_report_id, # 변동분 추적용 ID
                'conclusion': {
                    'Action': final_decision.get('Action', '관망'),
                    'Gauge_Bar': int(final_decision.get('Gauge_Bar', 50)),
                    'Max_Weight': final_decision.get('Max_Weight', '0%')
                },
                'reasoning': final_decision.get('reasoning', ["분석 결과 생성 중입니다."]),
                'ui_metrics': self._extract_ui_metrics(raw_data),
                'produced_by': final_decision.get('produced_by', 'Unknown Tier'),
                'timestamp': datetime.now().isoformat()
            }

            # 타입 하네스: reasoning이 리스트가 아니면 리스트로 변환
            if not isinstance(output['reasoning'], list):
                output['reasoning'] = [str(output['reasoning'])]

            # 6. 창고 입고 및 고객 배송
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
            
            logging.info(f"✅ {self.stock_name} 공정 완료 (Model: {output['produced_by']})")

        except Exception as e:
            logging.error(f"❌ {self.stock_name} 라인 붕괴: {e}")
            self.telegram.send_plain_message(f"🚨 <b>[ANDON]</b> {self.stock_name} 중단\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        """대시보드 렌더링용 지표 추출 (지능형 디폴트 적용)"""
        p_info = raw_data.get("price_info", {})
        curr_price = p_info.get("current_price", 0)
        return {
            "per_pbr": f"{p_info.get('per', 'N/A')} / {p_info.get('pbr', 'N/A')}",
            "rsi": 50, # 기술적 지표 계산 로직 필요 시 추가
            "peg": 1.0,
            "opm_yoy": "분석중",
            "order_backlog": p_info.get("dist_from_52w_high", "N/A"),
            "smart_money": "수급 체크중",
            "last_analyzed_price": curr_price # 변동성 트리거용 저장
        }

    def _archive_result(self, result):
        """결과 저장 (중복 제거 및 최신화)"""
        if not os.path.exists("data"): os.makedirs("data")
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: history = []
        
        # 동일 종목 이전 기록 제거 후 새 기록 삽입
        history = [h for h in history if h.get('stock_code') != result['stock_code']]
        history.append(result)
        
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)

def should_run_analysis(stock_code, current_price_data, history_list):
    """[SCM 지능형 제어] 공시 변동 및 주가 변동성(±5%) 감지"""
    # 1. 기존 이력 확인
    target_history = [h for h in history_list if h.get('stock_code') == stock_code]
    if not target_history:
        return True, "신규 종목 진입", "FIRST_RUN"

    last_record = target_history[-1]
    
    # 2. 공시 변동 체크 (DART ID 대조)
    current_report_id = DartApi().get_latest_report_id(stock_code)
    if current_report_id != last_record.get("data_fingerprint"):
        return True, "신규 공시 감지", current_report_id

    # 3. 주가 급변 트리거 (±5%)
    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    curr_price = current_price_data.get("current_price", 0)
    
    if last_price > 0:
        change_rate = abs((curr_price - last_price) / last_price) * 100
        if change_rate >= 5.0:
            return True, f"주가 급변 감지({change_rate:.1f}%)", current_report_id

    return False, "변동 사항 없음", current_report_id

if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Investment System 가동")
    
    # [1] 동적 수급 리스트 조달
    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()
    
    # [2] 기존 분석 이력 로드
    history = []
    if os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "r", encoding="utf-8") as f:
            history = json.load(f)

    # [3] 그룹별/종목별 생산 라인 가동
    kis = KISApi()
    for group_id, stocks in production_plan.items():
        for stock in stocks:
            try:
                # 현재 주가 데이터 프리-패치 (트리거 판단용)
                current_price_data = kis.get_stock_data(stock["code"])
                
                # 가동 여부 판단 (하네스 엔지니어링 제약)
                run_flag, reason, report_id = should_run_analysis(stock["code"], current_price_data, history)
                
                if run_flag:
                    engine = AgenticSCMEngine(stock["code"], stock["name"], stock["sector"])
                    engine.run_production_line(group_id, reason, report_id)
                    time.sleep(2) # API Rate Limit 보호
                else:
                    logging.info(f"☕ {stock['name']}: {reason} (공정 생략)")
                    
            except Exception as e:
                logging.error(f"⚠️ {stock['name']} 공정 준비 중 오류: {e}")

    logging.info("🏁 오늘의 모든 공정이 성공적으로 종료되었습니다.")
