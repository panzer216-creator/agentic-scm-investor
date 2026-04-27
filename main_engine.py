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
            bull, red = BullAgent("Bull").analyze(parser_res, self.sector), RedTeamAgent("Red").analyze(parser_res, self.sector)

            p_info = raw_data["price_info"]
            metrics = {"rsi": p_info.get("rsi", 50), "rs_score": p_info.get("rs_score", 1.0)}
            
            final = OrchestratorAgent().decide(parser_res, bull, red, self.stock_code, metrics)

            output = {
                'stock_code': self.stock_code, 'company_name': self.stock_name,
                'group_id': group_id, 'data_fingerprint': current_report_id,
                'conclusion': {'Action': final['Action'], 'Gauge_Bar': int(final['Gauge_Bar']), 'Max_Weight': final['Max_Weight']},
                'entry_point_guide': final['entry_point_guide'],
                'reasoning': final['reasoning'],
                'ui_metrics': {
                    "pbr_opm": f"{p_info['pbr']} / {p_info['opm_yoy']}",
                    "backlog": p_info['backlog_ratio'],
                    "turnover": p_info['inv_turnover'],
                    "rsi": p_info['rsi'],
                    "rs_score": p_info['rs_score'],
                    "smart_money": p_info['smart_money']
                },
                'produced_by': final['produced_by'], 'timestamp': datetime.now().isoformat()
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
