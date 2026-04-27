import logging

class OrchestratorAgent:
    def decide(self, sdp, bull, red, stock_code, metrics):
        """[SCM 직렬 매트릭스] 정성 분석 -> 정량 지표 -> 입체적 타점 가이드"""
        
        # 1. 에이전트 결과 추출
        def get_safe_gauge(res):
            try: return int(res.get("conclusion", {}).get("Gauge_Bar", 50))
            except: return 50
        
        g_bull = get_safe_gauge(bull)
        g_red = get_safe_gauge(red)
        avg_gauge = (g_bull + g_red) / 2

        # 2. 정량 지표 로드
        rsi = metrics.get("rsi", 50)
        rs_score = metrics.get("rs_score", 1.0)
        
        # 3. 판정 로직 (직렬 매트릭스)
        action = "관망"
        max_weight = "0%"

        if avg_gauge < 60: # 정성적 적격성 통과
            action = "분할 매수"
            max_weight = "10%"
            
            if rsi < 40 or rs_score > 1.2: # 타점 조건 충족
                action = "적극 매수"
                max_weight = "20%"

        if g_red >= 80: # 레드팀 강력 경고 시 오버라이드
            action = "비중 축소/관망"
            max_weight = "0%"

        # 4. [신설] 입체적 타점 가이드 생성
        entry_guide = self._generate_entry_guide(rsi, rs_score, action)

        return {
            "Action": action,
            "Gauge_Bar": avg_gauge,
            "Max_Weight": max_weight,
            "entry_point_guide": entry_guide,
            "reasoning": [
                f"[SCM/Qual] Bull({g_bull}) & Red({g_red}) 통합 리스크 {avg_gauge}",
                f"[Quant/Timing] RSI: {rsi}, RS Score: {rs_score:.2f}"
            ],
            "produced_by": f"{bull.get('produced_by', 'N/A')}/{red.get('produced_by', 'N/A')}"
        }

    def _generate_entry_guide(self, rsi, rs_score, action):
        """RSI와 RS Score를 결합한 전문가용 타점 지침"""
        if action == "비중 축소/관망":
            return "⚠️ 리스크 위험 신호 감지. 신규 진입을 금지하며 기존 보유 비중 축소 권장."
        
        # 시나리오 1: 황금 타점 (억울한 하락)
        if rsi <= 40 and rs_score >= 1.1:
            return "✨ [황금 타점] 지수 영향으로 일시 과매도되었으나 시장 대비 강한 하방 경직성 유지 중. 현 가격대 적극 매수 유효."
        
        # 시나리오 2: 주도주 눌림목 (가장 추천)
        if 40 < rsi <= 55 and rs_score >= 1.2:
            return "🚀 [주도주 눌림목] 초강세 주도주의 건강한 조정 구간. 장중 -2~3% 변동성 활용하여 선발대 진입 권장."
        
        # 시나리오 3: 추격 금지 (과열)
        if rsi >= 65:
            return "✋ [추격 매수 금지] 기술적 과열권 진입. 기업 가치는 높으나 단기 눌림목(RSI 50 부근) 대기 후 진입 권장."
        
        # 시나리오 4: 떨어지는 칼날 (주의)
        if rsi <= 35 and rs_score < 0.9:
            return "🚧 [관망 필요] 기술적 과매도 구간이나 시장 대비 낙폭이 과대함. 바닥 확인 전까지 진입 보류 및 추세 전환 확인 필요."
            
        return f"현재 {action} 판정 구간. RSI와 RS 수치가 중립적이므로 비중 가이드 내에서 분할 진입 추진."
