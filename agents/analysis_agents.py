import os
import json
import re
import logging
from google import genai
from google.genai import types

class BaseAnalysisAgent:
    # [검증 완료] 2026년 4월 기준 가장 안정적인 실가동 모델 리스트
    MODEL_CHAIN = [
        "gemini-3.1-pro",    # Plan A: 현존 최강 추론 엔진
        "gemini-2.5-pro",    # Plan B: 검증된 안정판 스테이블
        "gemini-2.5-flash",  # Plan C: 고속 처리용 백업
    ]

    def __init__(self, persona, weight=50):
        self.persona = persona
        self.weight = weight
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def _safe_parse_json(self, text: str) -> dict:
        """LLM 응답에서 마크다운 펜스를 제거하고 안전하게 JSON 추출"""
        fence = "`" * 3
        pattern = rf"{fence}(?:json)?\s*(\{{.*?\}})\s*{fence}"
        match = re.search(pattern, text, re.DOTALL)
        clean = match.group(1) if match else text.strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logging.warning(f"[{self.persona}] JSON 파싱 실패: {e}")
            return {"risk_score": 5, "summary": "파싱 에러로 인한 기본값 적용", "parse_error": True}

    def analyze(self, sdp_payload, sector):
        sys_prompt = f"""당신은 {self.persona} 성향의 SCM 투자 분석가입니다. (가중치: {self.weight}/100)
        1. 단기 뷰 (1~3M): 수급 및 노이즈
        2. 장기 뷰 (1~3Y): 본질 가치 및 수율
        3. 공급망 효과: 전후방 파급 효과
        반드시 JSON만 반환하고 risk_score(0~10)를 포함하세요."""

        for model_name in self.MODEL_CHAIN:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=str(sdp_payload),
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt,
                        response_mime_type="application/json"
                    )
                )
                return self._safe_parse_json(response.text)
            except Exception as e:
                logging.warning(f"[{self.persona}] {model_name} 실패: {e}. 폴백 시도.")

        return {"risk_score": 5, "summary": "전체 모델 체인 실패", "model_chain_exhausted": True}

class BullAgent(BaseAnalysisAgent): pass
class RedTeamAgent(BaseAnalysisAgent): pass
