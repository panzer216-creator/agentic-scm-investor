import os
import json
import logging

class ReviewAgent:
    def __init__(self):
        # 하네스 제약: 특정 에이전트의 과도한 편향 방지
        self.min_weight = 30
        self.max_weight = 70
        self.default_weights = {"bull": 50, "red": 50}

    def get_dynamic_weights(self, history_path, current_market_data):
        """
        [SCM 사후 검증] 과거 예측치와 실제 수익률을 대조하여 동적 가중치 산출
        """
        if not os.path.exists(history_path):
            return self.default_weights

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)

            if len(history) < 3:
                return self.default_weights

            bull_score = 0
            red_score = 0

            # 최근 5개 분석 공정 결과물 전수 조사
            for record in history[-5:]:
                stock_code = record.get("stock_code")
                # Main Engine에서 전달받은 현재가 데이터와 매칭
                current_info = current_market_data.get(stock_code, {})
                current_price = current_info.get("current_price", 0)
                
                # 분석 시점의 기록된 가격 확인
                last_analyzed_price = record.get("ui_metrics", {}).get("last_analyzed_price", 0)

                if last_analyzed_price == 0 or current_price == 0:
                    continue

                # 수익률(Return Rate) 계산
                return_rate = (current_price - last_analyzed_price) / last_analyzed_price * 100

                # [성과 평가 로직]
                if return_rate > 2.0:
                    # 주가 상승 시 Bull 에이전트 적중으로 간주
                    bull_score += 1
                elif return_rate < -2.0:
                    # 주가 하락 시 Red Team의 리스크 경고 적중으로 간주
                    red_score += 1

            # 가중치 산출 공정
            total_score = bull_score + red_score
            if total_score == 0:
                return self.default_weights

            # 점수 기반 비중 계산
            raw_bull_weight = int((bull_score / total_score) * 100)
            
            # 하네스 제약 적용 (30% ~ 70% 사이로 보정)
            final_bull = max(self.min_weight, min(self.max_weight, raw_bull_weight))
            final_red = 100 - final_bull

            logging.info(f"⚖️ 가중치 갱신 완료: Bull({final_bull}%) vs Red({final_red}%)")
            return {"bull": final_bull, "red": final_red}

        except Exception as e:
            logging.error(f"Review Agent 가동 오류: {e}")
            return self.default_weights
