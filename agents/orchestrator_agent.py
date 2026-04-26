from agents.review_agent import ReviewAgent

class OrchestratorAgent:
    def __init__(self):
        self.reviewer = ReviewAgent()

    def decide(self, sdp, bull, red):
        # 1. ReviewAgent로부터 과거 적중률 기반 가중치 수급
        weights = self.reviewer.get_current_weights("data/analysis_history.json")
        w_bull = weights.get("bull", 50) / 100
        w_red = weights.get("red", 50) / 100

        # 2. 하이브리드 판정 (수치적 결합)
        g_bull = int(bull.get("conclusion", {}).get("Gauge_Bar", 50))
        g_red = int(red.get("conclusion", {}).get("Gauge_Bar", 50))
        final_gauge = (g_bull * w_bull) + (g_red * w_red)

        # 3. 액션 규격화
        action = "관망"
        if final_gauge < 35: action = "적극 매수"
        elif final_gauge < 55: action = "분할 매수"
        elif final_gauge > 75: action = "매도/비중 축소"

        # 4. 논리 통합 (Harnessing reasoning)
        combined_why = [
            f"[Bull] {bull.get('reasoning', [''])[0]}",
            f"[Red] {red.get('reasoning', [''])[0]}"
        ]

        return {
            "Action": action,
            "Gauge_Bar": final_gauge,
            "Max_Weight": "20%" if action == "적극 매수" else "5%",
            "reasoning": combined_why,
            "produced_by": f"{bull.get('produced_by', 'N/A')}/{red.get('produced_by', 'N/A')}"
        }
