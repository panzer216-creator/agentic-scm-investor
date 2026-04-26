import os
import json
import re
import logging
from google import genai
from google.genai import types

class AgentHarness:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # [품질 최우선 공급망] Pro 모델을 전진 배치
        self.tiers = [
            "gemini-3.1-pro-preview",   # Tier 1: 고정밀 분석
            "gemini-2.5-pro",           # Tier 2: 검증된 안정성
            "gemini-3-flash-preview"    # Tier 3: 비상용 백업
        ]
        # [Poka-Yoke] 출력 규격(Schema) 정의
        self.output_schema = {
            "type": "OBJECT",
            "properties": {
                "conclusion": {
                    "type": "OBJECT",
                    "properties": {
                        "Action": {"type": "STRING"},
                        "Gauge_Bar": {"type": "INTEGER"},
                        "Max_Weight": {"type": "STRING"}
                    },
                    "required": ["Action", "Gauge_Bar", "Max_Weight"]
                },
                "reasoning": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                }
            },
            "required": ["conclusion", "reasoning"]
        }

    def call(self, prompt, system_instruction):
        for model_id in self.tiers:
            current_prompt = prompt
            # [Self-Correction] 모델별 최대 2회 재시도(Rework) 기회 부여
            for attempt in range(2):
                try:
                    logging.info(f"📡 [Harness] {model_id} 호출 (시도 {attempt + 1})...")
                    
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                            response_mime_type="application/json",
                            response_schema=self.output_schema # 스키마 강제 주입
                        )
                    )
                    
                    data = self._safe_parse(response.text)
                    
                    # [IQC 검수] 구조 및 데이터 타입 최종 확인
                    if self._validate_structure(data):
                        data["produced_by"] = model_id
                        return data
                    
                    # 규격 미달 시 피드백 생성 및 재작업 지시
                    logging.warning(f"⚠️ [Harness] {model_id} 규격 미달 발생. 자가 보정 시도.")
                    current_prompt = f"{prompt}\n\n[FEEDBACK]: Your previous response failed validation. Ensure 'conclusion' is a JSON OBJECT, not a string. Error: Schema Mismatch."
                    
                except Exception as e:
                    logging.warning(f"⚠️ [Harness] {model_id} 공정 장애: {str(e)[:50]}")
                    current_prompt = f"{prompt}\n\n[FEEDBACK]: Critical error occurred: {str(e)}. Fix the JSON structure."
                    continue

        return self._emergency_kit()

    def _validate_structure(self, data):
        """내용물이 진짜 서랍장(Dict)인지, 필수 칸막이가 있는지 검수"""
        if not isinstance(data, dict): return False
        conc = data.get("conclusion")
        if not isinstance(conc, dict): return False
        if not isinstance(conc.get("Gauge_Bar"), int): return False
        return True

    def _safe_parse(self, text):
        try:
            clean = re.sub(r'```json|```', '', text).strip()
            parsed = json.loads(clean)
            return parsed[0] if isinstance(parsed, list) else parsed
        except:
            return {}

    def _emergency_kit(self):
        return {
            "conclusion": {"Action": "관망", "Gauge_Bar": 50, "Max_Weight": "0%"},
            "reasoning": ["모든 공급망 단절 및 재작업 실패로 인한 비상 키트 가동"],
            "produced_by": "Emergency-Safety-Stock"
        }

class BaseAnalysisAgent:
    def __init__(self, persona):
        self.harness = AgentHarness()
        self.persona = persona

    def analyze(self, payload, sector):
        system_instruction = f"당신은 {self.persona}입니다. 반드시 주어진 JSON 스키마 규격을 엄수하십시오."
        prompt = self._build_prompt(payload, sector)
        return self.harness.call(prompt, system_instruction)

    def _build_prompt(self, payload, sector):
        raise NotImplementedError
