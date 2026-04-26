import os
import json
import re
import logging
from google import genai
from google.genai import types

class BaseAnalysisAgent:
    # [하네스 규격] 3단계 모델 수급 티어 고정
    MODEL_CHAIN = [
        "gemini-3-flash-preview",    # Tier 1: 주력 (고속/효율)
        "gemini-3.1-pro-preview",    # Plan B: 고도화 (심층 추론)
        "gemini-2.5-pro"             # Plan C: 안전재고 (안정성)
    ]

    def __init__(self, persona, weight=50):
        self.persona = persona
        self.weight = weight
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def analyze_with_harness(self, payload, sector):
        """하네스 엔지니어링: 3단계 폴백 및 데이터 규격 강제화"""
        prompt = self._build_prompt(payload, sector)
        
        for model_id in self.MODEL_CHAIN:
            try:
                logging.info(f"📡 [Harness] {self.persona} 에이전트가 {model_id} 호출 중...")
                
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2, # 변동성 제어
                        response_mime_type="application/json" # 출력 규격 강제
                    )
                )
                
                # [하네스 체결] 응답 텍스트를 딕셔너리로 변환 및 리스트 에러 방지
                raw_text = response.text
                processed_data = self._safe_parse_json(raw_text)
                
                # [부품 검수] 필수 필드 유무 확인
                if "conclusion" in processed_data and "reasoning" in processed_data:
                    # 어떤 모델이 생산했는지 메타데이터 부착
                    processed_data["produced_by"] = model_id
                    return processed_data
                
                logging.warning(f"⚠️ {model_id} 결과물 규격 미달. 다음 티어로 전환.")
                
            except Exception as e:
                logging.error(f"❌ {model_id} 공정 실패: {str(e)[:50]}")
                continue

        # 모든 티어 실패 시 비상 제품 반환
        return self._produce_emergency_kit()

    def _safe_parse_json(self, text: str) -> dict:
        """JSON 추출 및 리스트/딕셔너리 하네스 정합성 보장"""
        try:
            # 1. 마크다운 펜스 제거
            clean = re.sub(r'```json|```', '', text).strip()
            data = json.loads(clean)
            
            # 2. 리스트로 들어온 경우 0번 인덱스 추출 (오늘 발생한 에러 방지 핵심)
            if isinstance(data, list):
                data = data[0] if data else {}
                
            return data if isinstance(data, dict) else {}
        except:
            return {}

    def _produce_emergency_kit(self):
        return {
            "conclusion": {"Action": "분석 지연", "Gauge_Bar": 50, "Max_Weight": "0%"},
            "reasoning": ["모델 수급 일시 불안정으로 인한 자동 폴백 가동"],
            "produced_by": "Emergency-System"
        }

    def _build_prompt(self, payload, sector):
        # 각 에이전트별 상세 프롬프트는 하위 클래스에서 정의
        raise NotImplementedError
