import os
import json
from google import genai
from google.genai import types

class ParserAgent:
    def __init__(self):
        # 2.5 Pro 모델을 위한 최신 클라이언트 설정
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_id = "gemini-2.5-pro" # 높은 안정성과 정밀 분석을 위한 선택

    def _get_sector_keywords(self, sector):
        """섹터별 절대 누락 금지 키워드 (Hard-Lock 리스트)"""
        keywords = {
            "반도체": ["수율", "HBM", "유리 기판", "장비 반입", "재고자산", "파업", "보조금"],
            "2차전지": ["리튬", "니켈", "수주 잔고", "OEM", "증설", "가동률"],
            "자동차": ["운임", "리드타임", "판매 믹스", "환율", "관세"]
        }
        return keywords.get(sector, ["공급망", "실적", "파업", "원가", "규제"])

    def parse(self, raw_data, sector="반도체"):
        """SCM 관점의 고해상도 표준 데이터 팩(SDP) 생성"""
        target_keywords = self._get_sector_keywords(sector)
        
        # 2.5 Pro의 강력한 추론 능력을 활용한 시스템 지침
        system_prompt = f"""
        당신은 상장사 분석 전문 SCM 큐레이터입니다. 
        하부 에이전트들이 투자 의사결정을 내릴 수 있도록 '표준 데이터 팩(SDP)'을 생성하세요.

        [핵심 미션: 큐레이션 및 원문 보존]
        1. 요약하지 마세요. 대신 키워드({target_keywords}) 관련 문장은 앞뒤 문맥을 포함하여 가공 없이 'critical_snippets'에 담으세요.
        2. 모든 수치(%, 가격, 수량)는 'quant_data' 섹션에 리스트로 격리하세요.
        3. 뉴스는 매체명을, 공시는 접수번호를 반드시 출처(source)로 명시하세요.
        4. 데이터 간 논리적 괴리(예: 호재 보도 vs 외인 매도세)가 보이면 'anomaly_signals'에 기록하세요.

        [출력 규격] 반드시 유효한 JSON 형식으로만 답변하세요.
        """

        try:
            # 최신 SDK 호출 방식 (system_instruction 지원)
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=f"데이터 큐레이션 시작:\n{json.dumps(raw_data, ensure_ascii=False)}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            # 에러 발생 시 원인과 함께 부분 텍스트라도 반환하여 공정 중단 방지
            return {
                "error": f"Parsing failed: {str(e)}",
                "status": "Check API key or model availability"
            }
