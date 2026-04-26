import logging

class OrchestratorAgent:
    def decide(self, sdp, bull, red, stock_code, metrics):
        """[SCM 직렬 매트릭스] 정성(LLM) -> 정량(Value) -> 모멘텀(수급/차트) 순차 필터링"""
        
        # 1. 기초 게이지 안전 추출 (문자열 에러 원천 차단)
        def get_safe_gauge(agent_result):
            conc = agent_result.get("conclusion", {})
            if not isinstance(conc, dict): conc = {}
            try: return int(conc.get("Gauge_Bar", 50))
            except: return 50

        g_bull = get_safe_gauge(bull)
        g_red = get_safe_gauge(red)
        
        # 정성적 리스크 평균 (Bull/Red 1:1 반영)
        avg_gauge = (g_bull + g_red) / 2

        # 2. 정량 지표 로드 (metrics 딕셔너리에서 추출)
        rsi = metrics.get("rsi", 50)
        rs_score = metrics.get("rs_score", 1.0)
        inv_turnover = metrics.get("inv_turnover", "N/A")
        
        # 3. 직렬 관문(Gateway) 판정 로직
        action = "관망"
        max_weight = "0%"

        # [관문 1] 정성적 퀄리티: LLM 리스크 게이지가 60 미만인가? (투자 적격성)
        if avg_gauge < 60:
            action = "분할 매수"
            max_weight = "10%"
            
            # [관문 2] 가격 메리트 및 수급 모멘텀: RSI가 낮거나(저평가) 상대강도가 높은가(주도주)?
            if rsi < 40 or rs_score > 1.2:
                action = "적극 매수"
                max_weight = "20%"
        
        # [리스크 오버라이드] 레드팀의 강력한 경고가 있다면 모든 매수 보류
        if g_red >= 80:
            action = "비중 축소/관망"
            max_weight = "0%"

        # 4. 판정 논리 통합 (대시보드 출력용)
        reasoning = [
            f"📊 [정성/SCM] Bull({g_bull}) & Red({g_red}) 통합 리스크: {avg_gauge}",
            f"📈 [정량/모멘텀] RSI(14): {rsi}, 시장 대비 상대강도(RS): {rs_score}",
            f"💡 [최종 판정] 직렬 매트릭스 필터링 결과 '{action}' 결정 (Max {max_weight})"
        ]

        # 모델 코멘트 요약 추가
        if isinstance(bull.get("reasoning"), list) and bull["reasoning"]:
            reasoning.append(f"[Bull Point] {bull['reasoning'][0]}")
        if isinstance(red.get("reasoning"), list) and red["reasoning"]:
            reasoning.append(f"[Red Point] {red['reasoning'][0]}")

        return {
            "Action": action,
            "Gauge_Bar": avg_gauge,
            "Max_Weight": max_weight,
            "reasoning": reasoning,
            "produced_by": f"{bull.get('produced_by', 'N/A')}/{red.get('produced_by', 'N/A')}"
        }
