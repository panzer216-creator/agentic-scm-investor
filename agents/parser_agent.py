import re
import logging
from bs4 import BeautifulSoup

class ParserAgent:
    def __init__(self):
        # 분석 품질을 저해하는 자극적인 키워드 필터
        self.noise_keywords = ["역대급", "세계 최초", "폭등", "초비상", "충격"]

    def _clean_text(self, text, limit=800):
        """[전처리 공정] HTML 제거 및 텍스트 슬림화로 토큰 최적화"""
        if not text: return ""
        try:
            # 1. HTML 태그 제거
            soup = BeautifulSoup(text, "html.parser")
            clean_text = soup.get_text(separator=" ")
            # 2. 불필요한 공백 제거
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            # 3. 분석 효율을 위한 길이 제한
            return clean_text[:limit] + "..." if len(clean_text) > limit else clean_text
        except Exception as e:
            logging.warning(f"⚠️ 전처리 중 오류 발생: {e}")
            return str(text)[:limit]

    def parse(self, raw_data, sector):
        """[IQC] 원재료 규격 검수 및 표준 데이터 팩(SDP) 생성"""
        sdp = {"tier_1": [], "tier_2": [], "tier_3": []}

        # [DART 공시 전처리]
        dart_data = raw_data.get("dart_list", [])
        if not isinstance(dart_data, list): dart_data = []
        for report in dart_data:
            if not isinstance(report, dict): continue
            sdp["tier_1"].append({
                "title": report.get("report_nm", "공시"),
                "content": self._clean_text(report.get("content", ""), limit=1000)
            })

        # [뉴스 데이터 전처리 및 등급 분류]
        news_data = raw_data.get("news_list", [])
        if not isinstance(news_data, list): news_data = []

        for news in news_data:
            if not isinstance(news, dict): continue
            
            title = news.get("title", "")
            source = news.get("source", "Unknown")
            content = self._clean_text(news.get("description", ""), limit=500)
            
            item = {"title": title, "source": source, "content": content}
            
            # 노이즈 키워드 감지 시 격리(Tier 3)
            is_noise = any(kw in title for kw in self.noise_keywords)
            
            if is_noise:
                sdp["tier_3"].append(item)
            elif source in ["매일경제", "한국경제", "서울경제", "블룸버그", "로이터"]:
                sdp["tier_1"].append(item)
            else:
                sdp["tier_2"].append(item)

        return {"standard_data_pack": sdp}
