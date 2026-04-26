class ParserAgent:
    def __init__(self):
        # 노이즈를 걸러낼 트리거 키워드
        self.noise_keywords = ["역대급", "세계 최초", "폭등", "초비상", "충격"]

    def parse(self, raw_data, sector):
        sdp = {"tier_1": [], "tier_2": [], "tier_3": []}
        plan_b_flag = False

        # 공시 데이터는 가장 순도 높은 Tier 1 자재로 분류
        sdp["tier_1"].extend(raw_data.get("dart_list", []))

        # 뉴스 데이터 신뢰도 판별 로직
        for news in raw_data.get("news_list", []):
            title = news.get("title", "")
            source = news.get("source", "Unknown")
            
            is_noise = any(kw in title for kw in self.noise_keywords)
            
            if is_noise:
                sdp["tier_3"].append(news) # 노이즈 기사는 격리
            elif source == "Unknown":
                plan_b_flag = True
                sdp["tier_2"].append(news) # 출처 불명 시 보조 자재로 강등
            elif source in ["매일경제", "한국경제", "서울경제", "블룸버그", "로이터"]:
                sdp["tier_1"].append(news) # 메이저 언론사는 핵심 자재
            else:
                sdp["tier_2"].append(news) # 일반 뉴스는 보조 자재

        result = {"standard_data_pack": sdp}
        
        # IQC 예외 상황 발생 시 알림 메타데이터 추가
        if plan_b_flag:
            result["iqc_warning"] = "🚨 [IQC Warning] 출처 식별 불가 데이터 감지. 안전을 위해 일부 데이터 Tier 2 일괄 강등."
            
        return result
