import logging

class OrchestratorAgent:
    def decide(self, sdp, bull, red, stock_code, metrics):
        # 1. 정성 분석 퀄리티 (리스크 게이지 산출)
        def get_val(res):
            try: return int(res.get("conclusion", {}).get("Gauge_Bar", 50))
            except: return 50
        
        g_bull, g_red = get_val(bull), get_val(red)
        avg_gauge = (g_bull + g_red) / 2

        # 2. 정량 지표 로드
        rsi = metrics.get("rsi", 50)
        rs_score = metrics.get("rs_score", 1.0)
        
        # 3. [모순 해결] 동기화된 판정 및 타점 로직
        action = "관망"
        buy_target = "추세 및 지지선 확인 후 진입"
        sell_target = "리스크 관리 및 비중 조절"

        # 기초 펀더멘털 합격 시
        if avg_gauge < 60:
            action = "분할 매수"
            buy_target = "현 가격대에서 비중 내 분할 진입"
            sell_target = "RSI 70 돌파 시 차익 실현 검토"

            # 논리적 모순 제거: 과열권 진입 시 Action 강제 오버라이드
            if rsi >= 65:
                action = "조정 대기" # (기존 '분할 매수'와 충돌하던 부분 해결)
                buy_target = "과열 구간(추격 금지). RSI 50 부근 눌림목 대기"
                sell_target = "보유자 영역. 신규 진입 자제"
            
            # 주도주 황금 타점
            elif rsi <= 40 and rs_score >= 1.1:
                action = "적극 매수"
                buy_target = "시장 대비 초강세 + 과매도. 즉시 진입 유효"
                sell_target = "전고점 돌파 및 RS Score 꺾임 시 매도"
                
        # 레드팀 강력 경고 시
        if g_red >= 80 or (rsi <= 35 and rs_score < 0.9):
            action = "비중 축소"
            buy_target = "바닥 미확인. 신규 매수 절대 금지"
            sell_target = "반등 시 비중 축소 우선"

        # 4. 병목 펀더멘털 요약 (기업이 왜 병목인지 설명)
        bull_logic = bull.get('reasoning', ['병목 사유 분석 중'])[0]

        return {
            "Action": action,
            "Gauge_Bar": avg_gauge,
            "Max_Weight": "20%" if action == "적극 매수" else ("10%" if action == "분할 매수" else "0%"),
            "buy_target": buy_target,
            "sell_target": sell_target,
            "bottleneck_logic": bull_logic, # 핵심 병목 이유
            "produced_by": f"{bull.get('produced_by')}/{red.get('produced_by')}"
        }
