import os, json, logging, time
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

class AgenticSCMEngine:
    def __init__(self, stock_code, stock_name, sector):
        self.stock_code, self.stock_name, self.sector = stock_code, stock_name, sector
        self.history_path = "data/analysis_history.json"
        self.telegram = TelegramApi()

    def run_production_line(self, group_id, trigger_reason, current_report_id):
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

            # [수정 완료] buy_target, sell_target, bottleneck_logic 으로 변수명 완벽 매칭
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
                'bottleneck_logic': final.get('bottleneck_logic', '공급망 병목 사유 데이터 로딩 중...'),
                'ui_metrics': {
                    "pbr_opm": f"{p_info.get('pbr', 'N/A')} / {p_info.get('opm_yoy', 'N/A')}",
                    "backlog": p_info.get('backlog_ratio', 'N/A'),
                    "turnover": p_info.get('inv_turnover', 'N/A'),
                    "rsi": p_info.get('rsi', 50),
                    "rs_score": p_info.get('rs_score', 1.0),
                    "smart_money": p_info.get('smart_money', 'N/A')
                },
                'produced_by': final.get('produced_by', 'Unknown'), 
                'timestamp': datetime.now().isoformat()
            }
            self._archive_result(output)
            self.telegram.send_report(self.stock_name, output)
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

if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Engine v2.2 가동")
    plan = BucketFetcher().get_dynamic_production_plan()
    for g_id, stocks in plan.items():
        for s in stocks:
            AgenticSCMEngine(s["code"], s["name"], s["sector"]).run_production_line(g_id, "매일 정기 분석", "AUTO")
            time.sleep(1)
