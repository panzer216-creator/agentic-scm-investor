import os
import json
import time
from google import genai
from google.genai import types

class BaseAnalysisAgent:
    """모든 에이전트의 공통 기능을 담은 표준 설비"""
    def __init__(self, persona_name):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.persona_name = persona_name
        # Parser와 동일한 3단계 모델 체인 상속
        self.model_tiers = [
            "gemini-3.1-pro-preview", # 분석 단계는 정밀도를 위해 Pro를 우선순위로 설정 가능
            "gemini-1.5-pro",
            "gemini-3.1-flash"
        ]

    def analyze(self, sdp, sector="반도체"):
        system_instruction = self.get_persona_prompt(sector)
        
        for model_id in self.model_tiers:
            for retry in range(2):
                try:
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=f"데이터 팩 분석 시작: {json.dumps(sdp, ensure_ascii=False)}",
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json"
                        )
                    )
                    result = json.loads(response.text)
                    result["meta"] = {"agent": self.persona_name, "model": model_id}
                    return result
                except Exception as e:
                    print(f"⚠️ {self.persona_name} ({model_id}) 실패: {e}")
                    time.sleep(2)
        return {"error": f"{self.persona_name} 분석 최종 실패"}

    def get_persona_prompt(self, sector):
        raise NotImplementedError("하위 클래스에서 페르소나를 정의해야 합니다.")

class BullAgent(BaseAnalysisAgent):
    def get_persona_prompt(self, sector):
        return f"""당신은 {sector} 전문 성장주 투자 분석가(Bull)입니다. 
        데이터 팩에서 기회 요인, 수율 개선, 시장 확대 시그널을 찾아 투자 정당성을 확보하세요.
        최종 출력은 'rating'(1-10), 'rationale'(논거 3가지), 'target_view'를 포함한 JSON이어야 합니다."""

class RedTeamAgent(BaseAnalysisAgent):
    def get_persona_prompt(self, sector):
        return f"""당신은 {sector} 전문 리스크 관리자(Red Team)입니다.
        데이터 팩에서 파업, 공급망 훼손, 외인 이탈, 재고 과잉 등 숨겨진 위협을 찾아 공격하세요.
        특히 Bull이 놓칠 법한 '역발상 리스크'를 강조하세요.
        최종 출력은 'risk_score'(1-10), 'pitfalls'(위험요소 3가지), 'warning_view'를 포함한 JSON이어야 합니다."""
