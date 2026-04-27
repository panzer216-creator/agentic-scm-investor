class OrchestratorAgent:
    def decide(self, sdp, bull, red, stock_code, metrics):
        # 1. 정성 분석 점수 추출
        def get_val(res):
            try: return int(res.get("conclusion", {}).get("Gauge_Bar", 50))
            except: return 50
        
        g_bull, g_red = get_val(bull), get_val(red)
        avg_gauge = (g_bull + g_red) / 2

        # 2. 직렬 매트릭스 판정
        rsi, rs_score = metrics.get("rsi", 50), metrics.get("rs_score", 1.0)
        action, weight = "관망", "0%"

        if avg_gauge < 60: # 정성 통과
            action, weight = "분할 매수", "10%"
            if rsi < 40 or rs_score > 1.2: # 타점 포착
                action, weight = "적극 매수", "20%"

        if g_red >= 80: action, weight = "비중 축소", "0%"

        # 3. 입체적 타점 가이드 생성
        entry_point = self._generate_timing_guide(rsi, rs_score, action)

        return {
            "Action": action, "Gauge_Bar": avg_gauge, "Max_Weight": weight,
            "entry_point_guide": entry_point,
            "reasoning": [f"통합 리스크 {avg_gauge}", f"RSI {rsi} / RS {rs_score}"],
            "produced_by": f"{bull.get('produced_by')}/{red.get('produced_by')}"
        }

    def _generate_timing_guide(self, rsi, rs, action):
        if "축소" in action: return "⚠️ 리스크 과열. 신규 진입 금지 및 차익 실현 권장."
        if rsi <= 40 and rs >= 1.1: return "✨ [황금 타점] 지수 영향으로 일시적 과매도되었으나 강력한 하방 경직성 유지 중. 적극 매수."
        if 40 < rsi <= 55 and rs >= 1.2: return "🚀 [주도주 눌림목] 초강세 주도주의 건강한 조정. 장중 음봉 시 분할 진입 권장."
        if rsi >= 65: return "✋ [추격 금지] 과열권 진입. 기업 가치는 높으나 단기 조정(RSI 50 부근) 대기 요망."
        return f"현재 {action} 구간. 지표가 중립적이므로 정해진 비중 내에서 원칙 대응."
