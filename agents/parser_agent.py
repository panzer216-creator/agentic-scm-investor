import os
import json
import google.generativeai as genai

class ParserAgent:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        # 비용 효율과 속도를 위해 flash 모델 사용
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def _get_sector_keywords(self, sector):
        """섹터별 절대 누락 금지 키워드 정의 (Hard-Lock 리스트)"""
        keywords = {
            "반도체": ["수율", "HBM", "유리 기판", "장비 반입", "재고자산", "파업", "보조금"],
            "2차전지": ["리튬", "니켈", "수주 잔고", "OEM", "증설", "가동률"],
            "자동차": ["운임", "리드타임", "판매 믹스", "환율", "관세"]
        }
        return keywords.get(sector, ["공급망", "실적", "파업", "원가", "규제"])

    def parse(self, raw_data, sector="반도체"):
        """날것의 데이터를 SCM 관점의 표준 데이터 팩(SDP)으로 큐레이션"""
        target_keywords = self._get_sector_keywords(sector)
        
        system_prompt = f"""
        당신은 상장사 분석 전문 SCM 큐레이터입니다. 
        입력된 뉴스, 공시, 시세 데이터를 바탕으로 하부 에이전트들을 위한 '표준 데이터 팩(SDP)'을 생성하세요.

        [핵심 미션: 큐레이션 및 보존]
        1. 요약하지 말고 '추출'하세요. 
        2. 다음 키워드가 포함된 문장은 앞뒤 문맥을 포함하여 가공 없이 'critical_snippets'에 담으세요: {target_keywords}
        3. 모든 구체적 숫자(%, 가격, 수량)는 'quant_data' 섹션에 리스트로 격리하세요.
        4. 뉴스는 매체명을, 공시는 접수번호를 반드시 출처(source)로 명시하세요.
        5. 데이터 간 논리적 괴리(예: 호재 보도 vs 외인 매도세)가 보이면 'anomaly_signals'에 기록하세요.

        [출력 규격] JSON 형식만 허용.
        """

        prompt = f"아래 데이터를 {sector} 관점에서 정제하라:\n{json.dumps(raw_data, ensure_ascii=False)}"
        
        response = self.model.generate_content(
            [system_prompt, prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            return json.loads(response.text)
        except:
            return {
                "error": "SDP 생성 실패",
                "raw_text": response.text[:500]
            }
