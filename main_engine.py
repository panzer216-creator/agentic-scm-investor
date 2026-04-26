import os
import json
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
            # 런타임 에러 방지: 시세 데이터가 리스트로 올 경우 하네스 처리
            p_data = kis.get_stock_data(self.stock_code)
            result["price_info"] = p_data if isinstance(p_data, dict) else (p_data[0] if p_data else {})
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

            # 2. 데이터 정제 (Standard Data Pack 생성)
            parser = ParserAgent()
            parser_result = parser.parse(raw_data, self.sector)
            sdp_payload = parser_result.get("standard_data_pack", {})

            # 3. [Base 통제] 하네스 기반 에이전트 분석 가동
            # 에이전트 내부의 3-Tier Fallback(Flash -> 3.1 Pro -> 2.5 Pro)이 가동됩니다.
            bull_result = BullAgent("Bull").analyze_with_harness(sdp_payload, self.sector)
            red_result = RedTeamAgent("Red").analyze_with_harness(sdp_payload, self.sector)

            # 4. 의사결정 조립 (Orchestration)
            orc = OrchestratorAgent()
            final_decision = orc.decide(sdp_payload, bull_result, red_result)

            # 5. [하네스 규격 강제] 대시보드 및 아카이브용 최종 패킹
            output = {
                'stock_code': self.stock_code,
                'company_name': self.stock_name,
                'group_id': group_id,
                'data_fingerprint': current_report_id, # 변동분 추적용 핑거프린트
                'conclusion': {
                    'Action': final_decision.get('Action', '관망'),
                    'Gauge_Bar': int(final_decision.get('Gauge_Bar', 50)),
                    'Max_Weight': final_decision.get('Max_Weight', '0%')
                },
                'reasoning': final_decision.get('reasoning', ["분석 리포트 생성 중"]),
                'ui_metrics': self._extract_ui_metrics(raw_data),
                'produced_by': final_decision.get('produced_by', 'Unknown'), # 어떤 모델이 최종 생산했는지 기록
                'timestamp': datetime.now().isoformat()
            }

            # 타입 세이프티 하네스: reasoning 필드 타입 강제
            if not isinstance(output['reasoning'], list):
                output['reasoning'] = [str(output['reasoning'])]

            # 6. 창고 입고(Archive) 및 최종 배송(Telegram)
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
            
            logging.info(f"✅ {self.stock_name} 공정 완료 (Tier: {output['produced_by']})")

        except Exception as e:
            logging.error(f"❌ {self.stock_name} 라인 중단: {e}")
            self.telegram.send_plain_message(f"🚨 <b>[ANDON]</b> {self.stock_name} 공정 붕괴\n사유: {str(e)[:100]}")

    def _extract_ui_metrics(self, raw_data):
        """대시보드 렌더링 및 가격 변동 트리거용 지표 추출"""
        p_info = raw_data.get("price_info", {})
        curr_price = p_info.get("current_price", 0)
        return {
            "per_pbr": f"{p_info.get('per', 'N/A')} / {p_info.get('pbr', 'N/A')}",
            "rsi": 50,
            "peg": 1.0,
            "opm_yoy": "분석중",
            "order_backlog": p_info.get("dist_from_52w_high", "N/A"),
            "smart_money": "수급 분석중",
            "last_analyzed_price": curr_price # 차기 공정에서 ±5% 변동 체크용
        }

    def _archive_result(self, result):
        """데이터 창고 적재 (기존 기록 업데이트 방식)"""
        if not os.path.exists("data"): os.makedirs("data")
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: history = []
        
        # 동일 종목 중복 제거 후 최신 데이터 삽입
        history = [h for h in history if h.get('stock_code') != result['stock_code']]
        history.append(result)
        
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)

def should_run_analysis(stock_code, current_price_data, history_list):
    """[지능형 수급 제어] 공시 및 가격 변동성($ \pm 5\% $) 감지 로직"""
    # 1. 과거 이력 조회
    target_history = [h for h in history_list if h.get('stock_code') == stock_code]
    if not target_history:
        return True, "신규 종목 초기화", "INITIAL"

    last_record = target_history[-1]
    
    # 2. 공시 변동 체크 (DART 식별값 대조)
    current_report_id = DartApi().get_latest_report_id(stock_code)
    if current_report_id != last_record.get("data_fingerprint"):
        return True, "신규 공시/데이터 감지", current_report_id

    # 3. 주가 변동성 트리거 (분석 시점 대비 ±5% 이상 시 재분석)
    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    curr_price = current_price_data.get("current_price", 0)
    
    if last_price > 0:
        change_rate = abs((curr_price - last_price) / last_price) * 100
        if change_rate >= 5.0:
            return True, f"주가 변동성 임계치 초과 ({change_rate:.1f}%)", current_report_id

    return False, "변동 사항 없음 (공정 스킵)", current_report_id

if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Investment Engine v2.2 가동 시작")
    
    # [1] 동적 분석 대상 리스트 수급
    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()
    
    # [2] 창고 재고(기존 이력) 로드
    history = []
    if os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []

    # [3] 생산 라인 순차 가동
    kis = KISApi()
    for group_id, stocks in production_plan.items():
        for stock in stocks:
            try:
                # 가동 여부 판단을 위한 주가 프리-패치
                curr_price_info = kis.get_stock_data(stock["code"])
                
                # 중앙 통제실: 가동 여부 결정
                run_flag, reason, report_id = should_run_analysis(stock["code"], curr_price_info, history)
                
                if run_flag:
                    engine = AgenticSCMEngine(stock["code"], stock["name"], stock["sector"])
                    engine.run_production_line(group_id, reason, report_id)
                    time.sleep(2) # API 과부하 방지 (Cooldown)
                else:
                    logging.info(f"☕ {stock['name']}: {reason}")
                    
            except Exception as e:
                logging.error(f"⚠️ {stock['name']} 공정 준비 중 오류: {e}")

    logging.info("🏁 오늘의 모든 생산 공정이 성공적으로 종료되었습니다.")
