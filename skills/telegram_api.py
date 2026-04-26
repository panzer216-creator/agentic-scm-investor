import os
import requests

class TelegramApi:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_report(self, stock_name, decision):
        """오케스트레이터의 결과를 구조화하여 전송"""
        
        # 메시지 템플릿 구성 (SCM 스타일의 구조적 보고)
        text = (
            f"🏆 [투자 전략 리포트: {stock_name}]\n"
            f"───────────────────\n"
            f"📍 최종 의견: {decision.get('conclusion', {}).get('Action', 'N/A')}\n"
            f"📊 권장 비중: {decision.get('conclusion', {}).get('Target_Weight', 'N/A')}\n\n"
            f"💡 판단 근거 (Rationale):\n"
            f"- {decision.get('reasoning', [ '분석 실패' ])[0]}\n\n"
            f"🔍 핵심 모니터링:\n"
            f"{decision.get('conclusion', {}).get('Key_Monitoring_Point', '없음')}\n"
            f"───────────────────\n"
            f"🤖 분석 모델: {decision.get('meta', {}).get('model', 'N/A')}"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            res = requests.post(self.base_url, json=payload)
            return res.json()
        except Exception as e:
            print(f"❌ 텔레그램 발송 실패: {e}")
            return None
