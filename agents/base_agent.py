import os
import json
import re
import logging
from google import genai
from google.genai import types

class AgentHarness:
    """하네스 엔지니어링: 3단계 모델 수급 및 데이터 규격화 엔진"""
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.tiers = [
            "gemini-3-flash-preview",   # Tier 1: 주력 (고속/효율)
            "gemini-3.1-pro-preview",   # Plan B: 고도화 (심층 추론)
            "gemini-2.5-pro"            # Plan C: 안전재고 (안정성)
        ]

    def call(self, prompt, system_instruction):
        for model_id in self.tiers:
            try:
                logging.info(f"📡 [Harness] {model_id} 호출 중...")
                is_flash = "flash" in model_id
                
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1 if is_flash else 0.3,
                        response_mime_type="application/json"
                    )
                )
                
                # [데이터 검수] 어떤 형식이든 딕셔너리로 강제 변환
                data = self._safe_parse(response.text)
                if data and "conclusion" in data:
                    data["produced_by"] = model_id
                    return data
                
            except Exception as e:
                logging.warning(f"⚠️ [Harness] {model_id} 공정 장애: {str(e)[:50]}")
                continue
        
        return self._emergency_kit()

    def _safe_parse(self, text):
        try:
            clean = re.sub(r'```json|```', '', text).strip()
            parsed = json.loads(clean)
            # 리스트 에러 방지: 리스트가 입고되면 첫 번째 제품만 취함
            if isinstance(parsed, list):
                return parsed[0] if parsed else {}
            return parsed if isinstance(parsed, dict) else {}
        except:
            return {}

    def _emergency_kit(self):
        return {"conclusion": {"Action": "관망", "Gauge_Bar": 50}, "reasoning": ["모델 수급 불능으로 인한 비상 생성"], "produced_by": "Emergency"}

class BaseAnalysisAgent:
    """모든 분석 에이전트의 모태가 되는 표준 작업대"""
    def __init__(self, persona):
        self.harness = AgentHarness()
        self.persona = persona

    def analyze(self, payload, sector):
        system_instruction = f"당신은 {self.persona}입니다. 반드시 JSON 규격을 엄수하십시오."
        prompt = self._build_prompt(payload, sector)
        return self.harness.call(prompt, system_instruction)

    def _build_prompt(self, payload, sector):
        raise NotImplementedError
