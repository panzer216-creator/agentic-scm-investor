import logging

class OrchestratorAgent:
    def decide(self, sdp, bull, red, stock_code, metrics):
        def get_val(res):
            try: return int(res.get("conclusion", {}).get("Gauge_Bar", 50))
            except: return 50
        
        g_bull, g_red = get_val(bull), get_val(red)
        avg_gauge = (g_bull + g_red) / 2

        rsi = metrics.get("rsi", 50)
        rs_score = metrics.get("rs_score", 1.0)
        
        action, weight = "관망", "0%"
        buy_target = "추세 및 지지선 확인 후 진입"
        sell_target = "리스크 관리 및 비중 조절"

        if avg_gauge < 60:
            action, weight = "분할 매수", "10%"
            buy_target = "현 가격대에서 비중 내 분할 진입"
            sell_target = "RSI 70 돌파 시 차익 실현 검토"

            if rsi >= 65:
                action = "조정 대기"
                buy_target = "과열 구간(추격 금지). RSI 50 부근 눌림목 대기"
                sell_target = "보유자 영역. 신규 진입 자제"
            elif rsi <= 40 and rs_score >= 1.1:
                action, weight = "적극 매수", "20%"
                buy_target = "시장 대비 초강세 + 과매도. 즉시 진입 유효"
                sell_target = "전고점 돌파 및 RS Score 꺾임 시 매도"

        if g_red >= 80 or (rsi <= 35 and rs_score < 0.9):
            action, weight = "비중 축소", "0%"
            buy_target = "바닥 미확인. 신규 매수 절대 금지"
            sell_target = "반등 시 비중 축소 우선"

        bull_reasoning = bull.get('reasoning', ['분석 중'])
        bull_logic = bull_reasoning[0] if isinstance(bull_reasoning, list) and len(bull_reasoning) > 0 else str(bull_reasoning)

        return {
            "Action": action,
            "Gauge_Bar": avg_gauge,
            "Max_Weight": weight,
            "buy_target": buy_target,
            "sell_target": sell_target,
            "bottleneck_logic": bull_logic,
            "produced_by": f"{bull.get('produced_by', 'N/A')}/{red.get('produced_by', 'N/A')}"
        }
