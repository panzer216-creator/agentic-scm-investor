import os
import json
import logging

class ReviewAgent:
    def __init__(self):
        # 공장 초기화 기본 가중치
        self.default_weights = {"bull": 50, "red": 50}

    def get_current_weights(self, history_path):
        """과거 JSON 이력을 읽어 예측 적중률 기반의 동적 가중치 산출"""
        
        # 1. 파일 자체가 없으면 기본값 반환
        if not os.path.exists(history_path):
            logging.info("과거 분석 이력 없음. Factory Default(50:50) 가중치 적용.")
            return self.default_weights
            
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
                
            # 2. 비교할 만큼 충분한 데이터가 쌓이지 않았다면 기본값 반환
            if len(history) < 2:
                return self.default_weights

            # 3. 사후 검증 (Post-Mortem) 로직 전개
            # (향후 과제: 이 위치에 KIS API를 통해 일주일 전 주가와 현재 주가를 조회하고,
            # 과거의 action/target_weight와 대조하여 오차를 수리적으로 계산하는 코드가 탑재됩니다.)
            
            logging.info("사후 검증(Post-Mortem) 프로세스 통과. 현재는 안정성을 위해 50:50 보정.")
            return {"bull": 50, "red": 50} 
            
        except Exception as e:
            # 4. JSON 파싱 에러나 데이터 오염 시 Plan B 가동
            logging.error(f"Review Agent 오류 발생: {e}. 시스템 보호를 위해 가중치 롤백(50:50) 가동.")
            return self.default_weights
