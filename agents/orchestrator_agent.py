import os
import json
import time
from google import genai
from google.genai import types

class OrchestratorAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_tiers = [
            "gemini-3.1-pro-preview", # 최종 의사결정은 가장 똑똑한 모델이 담당
            "gemini-1.5-pro",
            "gemini-3-flash-preview"
        ]

    def decide(self, sdp, bull_result, red_result):
        system_instruction = """당신은 투자 의사결정 위원회(Orchestrator)입니다. 
        성장론자(Bull)와 리스크 관리자(Red Team)의 보고서를 대조하여 최종 투자 의견을 도출하세요.

        [수행 지침]
        1. 양측의 논리 중 '데이터 팩(SDP)'에 근거한 팩트가 무엇인지 가려내세요.
        2. Bull의 낙관론이 과한지, Red Team의 공포가 실질적인지 중재하세요.
        3. '왜' 이런 결론에 도달했는지에 대한 논리적 사고 과정을 반드시 먼저 설명하세요.
        4. 최종 결론은 'Action', 'Target_Weight', 'Key_Monitoring_Point'를 포함해야 합니다.

        [출력 형식] JSON format only.
        """

        context = {
            "standard_data_pack": sdp,
            "bull_report": bull_result,
            "red_team_report": red_result
        }

        for model_id in self.model_tiers:
            try:
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=f"최종 중재 및 의사결정 시작: {json.dumps(context, ensure_ascii=False)}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                print(f"⚠️ Orchestrator ({model_id}) 실패: {e}")
                time.sleep(2)
        
        return {"error": "최종 의사결정 공정 가동 실패"}
