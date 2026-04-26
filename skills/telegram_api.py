import os
import requests
import logging

class TelegramApi:
    def __init__(self):
        raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        # [검증 완료] 토큰 오염 방지를 위해 접두사만 정교하게 제거
        if raw_token.lower().startswith("bot"):
            self.token = raw_token[3:].strip()
        else:
            self.token = raw_token.strip()
            
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_report(self, stock_name, decision):
        action = decision.get('conclusion', {}).get('Action', 'N/A')
        weight = decision.get('conclusion', {}).get('Max_Weight', 'N/A')

        text = (
            f"🏆 [SCM V2.2 투자 전략: {stock_name}]\n"
            f"───────────────────\n"
            f"📍 최종 의견: {action}\n"
            f"📊 편입 한도(Max Cap): {weight}\n\n"
        )

        alerts = decision.get('plan_b_alerts', [])
        for alert in alerts:
            text += f"- {alert}\n"

        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        try:
            requests.post(self.base_url, json=payload)
        except Exception as e:
            logging.error(f"텔레그램 발송 실패: {e}")

    def send_plain_message(self, message):
        """비상 알림 전용 메서드"""
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(self.base_url, json=payload)
