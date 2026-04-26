import os
import json
import time
from google import genai
from google.genai import types

class ParserAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # SCM 전략: Plan A(고속) -> Plan B(고정밀) -> Plan C(비상 안정)
        self.model_tiers = [
            "gemini-3-flash-preview",      # Plan A: 표준 고속 엔진
            "gemini-3.1-flash-lite-preview", # Plan A-2: 비상 고속 엔진
            "gemini-3.1-pro-preview",      # Plan B: 고정밀 추론 엔진
            "gemini-2.5-pro"               # Plan C: 최종 안정성 보루
        ]

    def _get_sector_keywords(self, sector):
        keywords = {
            "반도체": ["수율", "HBM", "유리 기판", "장비 반입", "재고자산", "파업", "보조금"],
            "2차전지": ["리튬", "니켈", "수주 잔고", "OEM", "증설", "가동률"]
        }
        return keywords.get(sector, ["공급망", "실적", "파업", "원가", "규제"])

    def parse(self, raw_data, sector="반도체"):
        target_keywords = self._get_sector_keywords(sector)
        system_prompt = f"""당신은 SCM 데이터 큐레이터입니다. 
        1. 요약 금지. 키워드({target_keywords}) 관련 문장은 원문 그대로 'critical_snippets'에 보존.
        2. 수치 데이터는 'quant_data'에 격리.
        3. 반드시 JSON으로만 응답."""

        # 다층 방어 체계 가동 (Retry + Fallback)
        for model_id in self.model_tiers:
            for retry in range(2): # 각 모델당 최대 2회 시도
                try:
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=f"데이터 정제 시작: {json.dumps(raw_data, ensure_ascii=False)}",
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json"
                        )
                    )
                    sdp = json.loads(response.text)
                    sdp["meta"] = {"model_used": model_id, "status": "success"}
                    return sdp
                except Exception as e:
                    print(f"⚠️ {model_id} 시도 실패 ({retry+1}/2): {str(e)}")
                    time.sleep(2 ** retry) # 지수적 백오프 적용
            
            print(f"🔄 {model_id} 공급 불능. 다음 공급원({self.model_tiers[self.model_tiers.index(model_id)+1] if self.model_tiers.index(model_id)+1 < len(self.model_tiers) else 'None'})으로 전환합니다.")

        return {"error": "All models in the supply chain failed.", "status": "Critical Failure"}
