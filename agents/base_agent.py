import json
import logging
import time

class AgentHarness:
    def __init__(self):
        # 3단계 모델 수급 티어 설정 (2026-04 규격)
        self.tiers = [
            "gemini-3-flash-preview",   # Tier 1: 주력 (고속)
            "gemini-3.1-pro-preview",   # Plan B: 고도화 (추론)
            "gemini-2.5-pro"            # Plan C: 안전재고 (안정)
        ]

    def call_with_harness(self, prompt, system_instruction):
        """하네스 엔지니어링이 적용된 모델 호출 공정"""
        for tier_model in self.tiers:
            try:
                logging.info(f"📡 [Harness] {tier_model} 호출 시도...")
                
                # [Step 1] 모델 호출 (실제 호출 함수는 라이브러리에 맞게 연결)
                raw_response = self._execute_llm(tier_model, prompt, system_instruction)
                
                # [Step 2] 하네스 체결: 데이터 규격 정문화
                processed_data = self._bind_to_harness(raw_response)
                
                # [Step 3] 부품 검수: 필수 필드 존재 여부 확인
                if self._validate_harness(processed_data):
                    logging.info(f"✅ [Harness] {tier_model} 공정 성공")
                    return processed_data
                
                logging.warning(f"⚠️ [Harness] {tier_model} 결과물 규격 미달. 다음 티어로 전환.")
                
            except Exception as e:
                logging.error(f"❌ [Harness] {tier_model} 통신/런타임 실패: {e}")
                continue # 다음 티어로 폴백

        # [Final Fallback] 모든 티어 실패 시 생산하는 최소 규격 제품
        return self._produce_emergency_kit()

    def _bind_to_harness(self, response):
        """데이터를 딕셔너리 규격으로 강제 결합"""
        try:
            # 1. 문자열인 경우 JSON 파싱
            if isinstance(response, str):
                # JSON 문자열 추출 (마크다운 제거 로직 포함)
                json_str = response.split('```json')[-1].split('```')[0].strip()
                response = json.loads(json_str)

            # 2. 리스트인 경우 첫 번째 요소 추출 (오늘 발생한 에러 방지 핵심)
            if isinstance(response, list):
                response = response[0] if len(response) > 0 else {}

            return response if isinstance(response, dict) else {}
        except:
            return {}

    def _validate_harness(self, data):
        """필수 데이터 부품(Field) 검수"""
        required_fields = ['conclusion', 'reasoning']
        return all(field in data for field in required_fields)

    def _produce_emergency_kit(self):
        """비상용 리포트 생산"""
        return {
            "conclusion": {"Action": "데이터 재검토", "Gauge_Bar": 50, "Max_Weight": "0%"},
            "reasoning": ["모델 수급 일시 중단으로 인한 비상 공정 가동", "차기 가동 시 재분석 예정"],
            "ui_metrics": {"per_pbr": "N/A", "rsi": 50, "peg": 1.0, "opm_yoy": "N/A", "order_backlog": "N/A", "smart_money": "분석 불가"}
        }
