import os
import json
import re
import logging
from google import genai
from google.genai import types

class BaseAnalysisAgent:
    # [ECO-01] Graceful Degradation 모델 폴백 체인 구성
    MODEL_CHAIN = [
        "gemini-2.5-pro-preview-05-06", # 우선 가동 모델 (Plan A)
        "gemini-2.0-flash",             # Plan B
        "gemini-1.5-pro",               # Plan C
    ]

    def __init__(self, persona, weight=50):
        self.persona = persona
        self.weight = weight
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def _safe_parse_json(self, text: str) -> dict:
        """[ECO-02] LLM 응답에서 마크다운 펜스를 걷어내고 안전하게 JSON만 추출"""
        # UI 복사 버그 방지를 위해 백틱 3개를 문자열 연산으로 우회 생성
        fence = "`" * 3 
        pattern = rf"{fence}(?:json)?\s*(\{.*?\})\s*{fence}"
        
        match = re.search(pattern, text, re.DOTALL)
        clean = match.group(1) if match else text.strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logging.warning(f"[{self.persona}] JSON 파싱 실패: {e}. 기본값 딕셔너리 반환.")
            return {"risk_score": 5, "summary": "파싱 오류 발생. 기본 방어 논리 전개.", "parse_error": True}

    def analyze(self, sdp_payload, sector):
        sys_prompt = f"""당신은 {self.persona} 성향의 SCM 투자 분석가입니다. (현재 시스템 신뢰 가중치: {self.weight}/100)
        제공된 SDP(표준 데이터 팩)를 바탕으로 아래 3가지 매트릭스에 맞춰 입체적으로 분석하세요.
        
        [사고 구조 - SCM 관점 적용]
        1. 단기 뷰 (1~3M): 노이즈, 수급, 일회성 비용, 노동/파업 리스크
        2. 장기 뷰 (1~3Y): 본질 가치, 수율(Yield), CAPEX, 선단 공정 기술 로드맵
        3. 공급망(Context) 효과: 전방 고객사(수요)와 경쟁사 동향에 미칠 파급 효과 계산
        
        반드시 JSON 객체 하나만 반환하고, risk_score(0~10 사이의 숫자) 필드를 반드시 포함하세요."""
        
        last_error = None
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
                logging.info(f"[{self.persona}] 모델 '{model_name}' 사용 성공")
                return self._safe_parse_json(response.text)
            
            except Exception as e:
                last_error = e
                logging.warning(f"[{self.persona}] 모델 '{model_name}' 연산 실패: {e}. 폴백 모델 탐색 중...")

        logging.error(f"[{self.persona}] 전체 모델 체인 붕괴: {last_error}")
        return {"risk_score": 5, "summary": "모델 체인 전체 실패. 시스템 보호를 위한 기본값 리턴.", "model_chain_exhausted": True}

class BullAgent(BaseAnalysisAgent): pass
class RedTeamAgent(BaseAnalysisAgent): pass
