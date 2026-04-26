import os
import json
import re
import logging
from google import genai
from google.genai import types

class AgentHarness:
    """하네스 엔지니어링: 3단계 모델 수급 및 데이터 규격화 엔진"""
    def __init__(self):
        # 2026년 4월 기준 실가동 모델 리스트
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.tiers = [
            "gemini-3-flash-preview",   # Tier 1: 주력 (고속/효율)
            "gemini-3.1-pro-preview",   # Plan B: 고도화 (심층 추론)
            "gemini-2.5-pro"            # Plan C: 안전재고 (안정성)
        ]

    def call(self, prompt, system_instruction):
        """모델 체인 가동 및 폴백 로직"""
        for model_id in self.tiers:
            try:
                logging.info(f"📡 [Harness] {model_id} 호출 시도 중...")
                is_flash = "flash" in model_id
                
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1 if is_flash else 0.3, # Flash는 변동성 억제
                        response_mime_type="application/json"
                    )
                )
                
                # [하네스 체결] 날것의 응답을 표준 딕셔너리로 강제 변환
                data = self._safe_parse(response.text)
                
                # [부품 검수] 필수 규격 확인
                if data and "conclusion" in data:
                    data["produced_by"] = model_id
                    return data
                
                logging.warning(f"⚠️ [Harness] {model_id} 결과물 규격 미달. 다음 티어로 전환.")
                
            except Exception as e:
                logging.warning(f"⚠️ [Harness] {model_id} 공정 장애: {str(e)[:50]}")
                continue # 다음 티어로 자동 폴백
        
        return self._emergency_kit()

    def _safe_parse(self, text):
        """리스트 객체 에러 및 JSON 파싱 에러 원천 차단"""
        try:
            # 1. 마크다운 펜스 제거
            clean = re.sub(r'```json|```', '', text).strip()
            parsed = json.loads(clean)
            
            # 2. 리스트로 입고되었을 경우 첫 번째 제품만 취함 (오늘 발생한 에러 해결 핵심)
            if isinstance(parsed, list):
                return parsed[0] if parsed else {}
                
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            logging.error("❌ 하네스 파싱 실패: 비표준 데이터 입고")
            return {}

    def _emergency_kit(self):
        """모든 공급망 단절 시 제공되는 비상 리포트"""
        return {
            "conclusion": {"Action": "관망", "Gauge_Bar": 50, "Max_Weight": "0%"},
            "reasoning": ["시스템 내 모든 모델 수급 라인 장애로 인한 비상 모드 가동"],
            "produced_by": "Emergency-Safety-Stock"
        }

class BaseAnalysisAgent:
    """모든 특화 에이전트의 부모 클래스 (표준 공정 정의)"""
    def __init__(self, persona):
        self.harness = AgentHarness()
        self.persona = persona

    def analyze(self, payload, sector):
        """에이전트별 특화 분석 실행"""
        # 하네스 제약 조건: Flash 모델 등에 대한 강력한 페널티 프롬프트 주입
        system_instruction = f"당신은 {self.persona}입니다. 반드시 JSON 규격을 엄수하십시오. 설명 없이 데이터만 출력하십시오."
        prompt = self._build_prompt(payload, sector)
        return self.harness.call(prompt, system_instruction)

    def _build_prompt(self, payload, sector):
        """하위 클래스에서 각자의 논리에 맞게 구현"""
        raise NotImplementedError
