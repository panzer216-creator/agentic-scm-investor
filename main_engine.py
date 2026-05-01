import os, sys, json, logging, time
from datetime import datetime
from skills.kis_api import KISApi
from skills.naver_api import NaverNewsApi
from skills.dart_api import DartApi
from skills.telegram_api import TelegramApi
from skills.bucket_fetcher import BucketFetcher
from agents.parser_agent import ParserAgent
from agents.analysis_agents import BullAgent, RedTeamAgent
from agents.orchestrator_agent import OrchestratorAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def is_holiday():
    """주말(토,일) 체크 로직 (향후 공휴일 API 연동 가능)"""
    return datetime.now().weekday() >= 5

class AgenticSCMEngine:
    def __init__(self, stock_code, stock_name, sector):
        self.stock_code, self.stock_name, self.sector = stock_code, stock_name, sector
        self.history_path = "data/analysis_history.json"
        self.telegram = TelegramApi()

    def run_production_line(self, group_id, current_report_id):
        try:
            raw_data = {"price_info": KISApi().get_stock_data(self.stock_code)}
            raw_data["news_list"] = NaverNewsApi().search_stock_news(self.stock_name)
            raw_data["dart_list"] = DartApi().get_recent_reports(self.stock_code)

            parser_res = ParserAgent().parse(raw_data, self.sector).get("standard_data_pack", {})
            bull = BullAgent("Bull").analyze(parser_res, self.sector)
            red = RedTeamAgent("Red").analyze(parser_res, self.sector)

            p_info = raw_data["price_info"]
            metrics = {"rsi": p_info.get("rsi", 50), "rs_score": p_info.get("rs_score", 1.0)}
            
            final = OrchestratorAgent().decide(parser_res, bull, red, self.stock_code, metrics)

            output = {
                'stock_code': self.stock_code, 
                'company_name': self.stock_name,
                'group_id': group_id, 
                'data_fingerprint': current_report_id,
                'conclusion': {
                    'Action': final.get('Action', '관망'), 
                    'Gauge_Bar': int(final.get('Gauge_Bar', 50)), 
                    'Max_Weight': final.get('Max_Weight', '0%')
                },
                'buy_target': final.get('buy_target', '지표 산출 중'),
                'sell_target': final.get('sell_target', '지표 산출 중'),
                'bottleneck_logic': final.get('bottleneck_logic', '공급망 병목 사유 분석 중...'),
                'ui_metrics': {
                    "pbr_opm": f"{p_info.get('pbr', 'N/A')} / {p_info.get('opm_yoy', 'N/A')}",
                    "backlog": p_info.get('backlog_ratio', 'N/A'),
                    "turnover": p_info.get('inv_turnover', 'N/A'),
                    "rsi": p_info.get('rsi', 50),
                    "rs_score": p_info.get('rs_score', 1.0),
                    "smart_money": p_info.get('smart_money', 'N/A'),
                    "last_analyzed_price": p_info.get("current_price", 0)
                },
                'produced_by': final.get('produced_by', 'Unknown'), 
                'timestamp': datetime.now().isoformat()
            }
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
            logging.info(f"✅ {self.stock_name} 심층 분석 완료")
        except Exception as e:
            logging.exception(f"❌ {self.stock_name} 중단: {e}")

    def _archive_result(self, result):
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                try: history = json.load(f)
                except: pass
        history = [h for h in history if h.get('stock_code') != result['stock_code']]
        history.append(result)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)

def should_run_analysis(stock_code, current_price_data, history_list):
    target_history = [h for h in history_list if h.get('stock_code') == stock_code]
    if not target_history: return True, "신규 종목 진입", "INITIAL"
    
    last_record = target_history[-1]
    current_report_id = DartApi().get_latest_report_id(stock_code)
    if current_report_id != last_record.get("data_fingerprint"): return True, "신규 공시 감지", current_report_id

    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    curr_price = current_price_data.get("current_price", 0) if isinstance(current_price_data, dict) else 0
    rsi = current_price_data.get("rsi", 50) if isinstance(current_price_data, dict) else 50

    if rsi <= 40: return True, f"RSI 침체 진입 ({rsi})", current_report_id
    if last_price > 0 and curr_price > 0:
        if abs((curr_price - last_price) / last_price) * 100 >= 5.0: return True, "주가 5% 이상 급변", current_report_id
    return False, "변동 사항 없음", current_report_id

if __name__ == "__main__":
    run_mode = os.getenv("RUN_MODE", "AUTO") # GitHub Actions에서 AUTO 또는 MANUAL 전달
    logging.info(f"🏭 Agentic SCM Engine 가동 (모드: {run_mode})")

    if run_mode == "AUTO" and is_holiday():
        logging.info("☕ 휴장일(주말/공휴일)입니다. 비용 절감을 위해 시스템 가동을 스킵합니다.")
        sys.exit(0)

    plan = BucketFetcher().get_dynamic_production_plan()
    if not plan: sys.exit(1)

    history = []
    if os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: pass

    kis, tg = KISApi(), TelegramApi()
    
    for g_id, stocks in plan.items():
        for s in stocks:
            try:
                curr_price_info = kis.get_stock_data(s["code"])
                run_flag, reason, report_id = should_run_analysis(s["code"], curr_price_info, history)
                
                if run_flag:
                    if run_mode == "AUTO":
                        # Track 1: LLM 호출 없이 무료 API로 감시 후 알람만 발송
                        tg.send_plain_message(f"🚨 [센티널 포착] {s['name']}\n사유: {reason}\n대시보드에서 '심층 분석'을 가동하십시오.")
                        logging.info(f"🔔 {s['name']} 알람 발송 완료 ({reason})")
                    else:
                        # Track 2: 대시보드 버튼 클릭 시에만 LLM 풀가동
                        AgenticSCMEngine(s["code"], s["name"], s["sector"]).run_production_line(g_id, report_id)
                        time.sleep(1)
            except Exception as e:
                logging.exception(f"⚠️ {s['name']} 오류: {e}")
