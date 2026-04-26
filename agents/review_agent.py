import os
import json
import logging

class ReviewAgent:
    def __init__(self):
        # 최소/최대 가중치 제약 (절연 파괴 방지)
        self.min_weight = 30
        self.max_weight = 70
        self.default_weights = {"bull": 50, "red": 50}

    def get_dynamic_weights(self, history_path, current_market_data):
        """
        [SCM 사후 검증] 과거 예측치와 실제 수익률을 대조하여 가중치 산출
        """
        if not os.path.exists(history_path):
            return self.default_weights
            
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            if len(history) < 3: # 최소 표본 확보 전까지는 기본값
                return self.default_weights

            bull_score = 0
            red_score = 0
            
            # 최근 5개 공정 결과물 전수 조사
            for record in history[-5:]:
                # 1. 분석 당시 대비 현재 수익률 계산
                last_price = record.get("ui_metrics", {}).get("last_analyzed_price", 0)
                # current_market_data는 Main Engine에서 주입받음
                current_price = current_market_data.get(record['stock_code'], {}).get('price', last_price)
                
                if last_price == 0: continue
                return_rate = (current_price - last_price) / last_price * 100
                
                # 2. Bull/Red 기여도 산출 로직
                # 수익률이 플러스면 Bull 가점, 마이너스면 Red(리스크 감지) 가점
                if return_rate > 2.0: bull_score += 1
                elif return_rate < -2.0: red_score += 1

            # 3. 가중치 정규화 (Softmax 또는 단순 비중)
            total = bull_score + red_score
            if total == 0: return self.default_weights
            
            new_bull = int((bull_score / total) * 100)
            new_red = 100 - new_bull
            
            # 4. 하네스 제약 적용 (30% ~ 70% 사이로 보정)
            new_bull = max(self.min_weight, min(self.max_weight, new_bull))
            new_red = 100 - new_bull
            
            logging.info(f"⚖️ 가중치 조정 완료 -> Bull: {new_bull}, Red: {new_red}")
            return {"bull": new_bull, "red": new_red}

        except Exception as e:
            logging.error(f"Review Agent 가동 붕괴: {e}")
            return self.default_weights
