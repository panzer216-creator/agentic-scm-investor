from agents.review_agent import ReviewAgent

class OrchestratorAgent:
    def __init__(self):
        self.reviewer = ReviewAgent()

    def decide(self, sdp, bull, red, stock_code, current_price):
        # 1. ReviewAgent 동적 가중치 수급
        current_market_data = {stock_code: {"current_price": current_price}}
        weights = self.reviewer.get_dynamic_weights("data/analysis_history.json", current_market_data)
        w_bull = weights.get("bull", 50) / 100
        w_red = weights.get("red", 50) / 100

        # 2. [이중 절연] 불량 부품(문자열 등)을 빈 서랍장으로 강제 치환
        def get_safe_gauge(agent_result):
            conc = agent_result.get("conclusion", {})
            if not isinstance(conc, dict): 
                conc = {} # 문자열 환각 발생 시 빈 딕셔너리로 절연
            try:
                return int(conc.get("Gauge_Bar", 50))
            except:
                return 50 # 숫자가 아닐 경우 기본값 50 반환

        g_bull = get_safe_gauge(bull)
        g_red = get_safe_gauge(red)

        # 3. 하이브리드 판정
        final_gauge = (g_bull * w_bull) + (g_red * w_red)

        # 4. 액션 규격화
        action = "관망"
        if final_gauge < 35: action = "적극 매수"
        elif final_gauge < 55: action = "분할 매수"
        elif final_gauge > 75: action = "매도/비중 축소"

        # 5. 논리 통합
        combined_why = [
            f"[Bull] {bull.get('reasoning', ['정보 없음'])[0]}",
            f"[Red] {red.get('reasoning', ['정보 없음'])[0]}"
        ]

        return {
            "Action": action,
            "Gauge_Bar": final_gauge,
            "Max_Weight": "20%" if action == "적극 매수" else "5%",
            "reasoning": combined_why,
            "produced_by": f"{bull.get('produced_by', 'N/A')}/{red.get('produced_by', 'N/A')}"
        }
