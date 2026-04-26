import json
from agents.base_agent import BaseAnalysisAgent

class BullAgent(BaseAnalysisAgent):
    """성장 동력 및 SCM 강점 분석 전문가 (Bull Perspective)"""
    def __init__(self, persona="Global SCM & Investment Strategist (Optimist)"):
        super().__init__(persona)

    def _build_prompt(self, payload, sector):
        return f"""
        [산업 섹터] {sector}
        [입고 데이터] {json.dumps(payload, ensure_ascii=False)}
        
        [분석 지시]
        1. 위 데이터를 바탕으로 해당 기업의 SCM적 강점과 시장 지배력 확대 가능성을 분석하십시오.
        2. 'conclusion' 내 'Gauge_Bar'는 0(강력매수)에서 100(매도) 사이로 산정하십시오.
        3. 'reasoning'은 반드시 2개 이상의 불렛포인트 리스트로 작성하십시오.
        """

class RedTeamAgent(BaseAnalysisAgent):
    """병목 현상 및 리스크 비판 전문가 (Red Team Auditor)"""
    def __init__(self, persona="Red Team Risk Auditor (Skeptic)"):
        super().__init__(persona)

    def _build_prompt(self, payload, sector):
        return f"""
        [산업 섹터] {sector}
        [입고 데이터] {json.dumps(payload, ensure_ascii=False)}
        
        [비판적 분석 지시]
        1. 위 데이터에서 가려진 리스크, 공급망 병목, 경쟁사 위협을 날카롭게 지적하십시오.
        2. 낙관적 전망을 배제하고 '최악의 시나리오' 관점에서 분석하십시오.
        3. 'conclusion'과 'reasoning' 규격은 표준 하네스 규격에 맞추십시오.
        """
