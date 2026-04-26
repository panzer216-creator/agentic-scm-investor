class OrchestratorAgent:
    def decide(self, sdp_payload, bull_result, red_result):
        
        # 1. Red Team의 리스크 스코어 안전 추출
        try:
            risk_score = float(red_result.get("risk_score", 5))
            is_valid_score = True
        except (ValueError, TypeError):
            risk_score = 10  # 파싱 실패 시 자산 보호를 위해 최악의 리스크로 가정
            is_valid_score = False

        # 2. SCM 안전 재고 기반 자산 배분(Max Cap) 룰베이스
        if risk_score >= 8.0:
            target_weight = 5
            action = "전면 매도 또는 관망"
        elif risk_score >= 5.0:
            target_weight = 15
            action = "비중 축소 (현금 안전재고 확보)"
        else:
            target_weight = 30
            action = "매수 가능 구간"

        # 3. HTML UI 게이지 연동을 위한 100분위 스케일 변환
        gauge_value = int((risk_score / 10.0) * 100)

        decision = {
            "conclusion": {
                "Action": action,
                "Max_Weight": f"{target_weight}%",
                "Gauge_Bar": gauge_value
            },
            "reasoning": [
                f"Red Team 산출 리스크: {risk_score}/10",
                "안전 재고 알고리즘에 따른 기계적 한도 통제 적용"
            ]
        }

        # 4. 수치 연산 실패에 따른 Plan B 가동 여부 체킹
        if not is_valid_score:
            decision["conclusion"]["Max_Weight"] = "0% (강제 방어)"
            decision["andon_alert"] = "🚨 [Allocation Warning] 리스크 수치 산출 오류 발생. 자산 보호를 위해 '비중 0% 강제 락오프' 적용."

        return decision
