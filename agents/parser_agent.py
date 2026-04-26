
import os
import json
import google.generativeai as genai

class ParserAgent:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def get_system_prompt(self, sector="반도체"):
        """섹터별 맞춤형 큐레이션 지침 생성"""
        return f"""
        당신은 전문 SCM 데이터 큐레이터입니다. 입력된 뉴스, 공시, 시세 데이터를 분석하여 
        하부 분석 에이전트들이 사용할 '표준 데이터 팩(SDP)'을 생성하세요.

        [수행 지침]
        1. 요약하지 마세요. 대신 '추출'하세요.
        2. '{sector}' 섹터의 핵심 키워드(수율, HBM, 공급망, 가동률, 파업, 원재료가 등)가 포함된 문장은 
           앞뒤 문맥을 포함하여 원형 그대로 'critical_snippets' 섹션에 담으세요.
        3. 모든 수치(숫자, %, 가격)는 'quant_data' 섹션에 리스트로 격리하세요.
        4. 뉴스 매체명과 공시 번호를 반드시 데이터의 출처로 병기하세요.
        5. 데이터 간 모순(예: 호재 뉴스 vs 외인 매도)이 발견되면 'anomaly_signals'에 기록하세요.

        [출력 형식] JSON format only.
        """

    def parse(self, raw_data, sector="반도체"):
        """날것의 데이터를 정제된 SDP로 변환"""
        prompt = f"""
        아래 데이터를 바탕으로 {sector} 관점의 표준 데이터 팩을 생성해줘.
        
        [Raw Data]
        {json.dumps(raw_data, ensure_ascii=False)}
        """
        
        response = self.model.generate_content(
            [self.get_system_prompt(sector), prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            return json.loads(response.text)
        except:
            return {"error": "Parsing failed", "raw_response": response.text}

# --- [단독 검증 모듈] ---
if __name__ == "__main__":
    print("🚀 Parser Agent 큐레이션 테스트 시작...")
    
    # 가상의 raw_data (실제로는 skills/ 모듈들에서 합쳐져서 들어옴)
    sample_data = {
        "stock_info": {"name": "삼성전자", "price": 75000, "supply": "외인 -500억"},
        "news": [{"title": "삼성전자 파업 위기, 반도체 수율에 치명적", "media": "경제신문"}],
        "dart": [{"title": "분기보고서(가동률 90% 초과)", "receipt_no": "20240101"}]
    }
    
    parser = ParserAgent()
    sdp = parser.parse(sample_data, sector="반도체")
    
    print("\n📦 생성된 표준 데이터 팩(SDP) 구조:")
    print(json.dumps(sdp, indent=2, ensure_ascii=False))
