import os
import json
import re
import logging
from google import genai
from google.genai import types

class BaseAnalysisAgent:
    # [하네스 규격] 사용자 합의된 3단계 모델 수급 티어
    MODEL_CHAIN = [
        "gemini-3-flash-preview",    # Tier 1: 주력 (고속)
        "gemini-3.1-pro-preview",    # Plan B: 고도화 (추론)
        "gemini-2.5-pro"             # Plan C: 안전재고 (안정)
    ]

    def __init__(self, persona):
        self.persona = persona
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def analyze_with_harness(self, payload, sector):
        """하네스 엔지니어링: 3단계 폴백 및 데이터 타입 강제화"""
        prompt = self._build_prompt(payload, sector)
        
        for model_id in self.MODEL_CHAIN:
            try:
                # [하네스 제약] Flash 모델일 경우 페널티 프롬프트 및 저전력(Temperature) 설정
                is_flash = "flash" in model_id
                system_instruction = self._get_harness_instruction(is_flash)
                
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1 if is_flash else 0.3, # Flash는 변동성 억제
                        response_mime_type="application/json"
                    )
                )
                
                # [하네스 바인딩] 리스트 에러 방지 처리 (핵심)
                processed = self._safe_parse_harness(response.text)
                
                if "conclusion" in processed and "reasoning" in processed:
                    processed["produced_by"] = model_id
                    return processed
                    
                logging.warning(f"⚠️ {model_id} 결과물 규격 미달. 다음 티어로 전환.")
                
            except Exception as e:
                logging.warning(f"⚠️ {model_id} 공정 장애: {str(e)[:50]}")
                continue
        
        return self._emergency_fallback()

    def _get_harness_instruction(self, strict):
        base = f"당신은 {self.persona} 전문가입니다. SCM 관점에서 투자를 분석하십시오."
        if strict:
            # 하네스 엔지니어링: Flash 모델용 강력한 규격 준수 제약
            base += "\nCRITICAL: 반드시 JSON 형식으로만 답변하십시오. 부연 설명 없이 오직 데이터만 출력해야 합니다. 이를 어길 시 시스템이 중단됩니다."
        return base

    def _safe_parse_harness(self, text):
        """어떤 데이터가 들어와도 딕셔너리로 강제 결합"""
        try:
            clean = re.sub(r'```json|```', '', text).strip()
            data = json.loads(clean)
            # 리스트 타입으로 입고되었을 경우 첫 번째 제품만 취함 (오늘 발생한 에러 해결)
            if isinstance(data, list):
                return data[0] if data else {}
            return data if isinstance(data, dict) else {}
        except:
            return {}

    def _emergency_fallback(self):
        return {
            "conclusion": {"Action": "관망", "Gauge_Bar": 50, "Max_Weight": "0%"},
            "reasoning": ["모든 모델 수급 라인 장애로 인한 비상 리포트"],
            "produced_by": "System-Failure"
        }

# 구체적 에이전트 구현
class BullAgent(BaseAnalysisAgent):
    def _build_prompt(self, payload, sector):
        return f"섹터: {sector}\n데이터: {json.dumps(payload)}\n성장 동력과 강점을 중심으로 분석하십시오."

class RedTeamAgent(BaseAnalysisAgent):
    def _build_prompt(self, payload, sector):
        return f"섹터: {sector}\n데이터: {json.dumps(payload)}\n병목 현상과 리스크를 중심으로 비판하십시오."
