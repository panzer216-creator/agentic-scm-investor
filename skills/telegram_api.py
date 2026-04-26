import os
import requests
import logging

class TelegramApi:
    def __init__(self):
        raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        # 실수로 'bot' 글자를 포함해 입력해도 시스템이 알아서 정제 (Poka-yoke)
        self.token = raw_token.replace("bot", "").strip() 
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_report(self, stock_name, decision):
        """정상적인 분석 결과를 구조화하여 배송 및 Plan B 알림 점등"""
        action = decision.get('conclusion', {}).get('Action', 'N/A')
        weight = decision.get('conclusion', {}).get('Max_Weight', 'N/A')
        
        text = (
            f"🏆 [SCM V2.1 투자 전략: {stock_name}]\n"
            f"───────────────────\n"
            f"📍 최종 의견: {action}\n"
            f"📊 편입 한도(Max Cap): {weight}\n\n"
        )
        
        # 시스템 우회(Plan B) 발생 시 붉은색 경고등 점등
        alerts = decision.get('plan_b_alerts', [])
        if alerts:
            text += "⚠️ <b>[비상 가동 알림 (Plan B)]</b>\n"
            for alert in alerts:
                text += f"- {alert}\n"
            text += "───────────────────\n"

        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}

        try:
            res = requests.post(self.base_url, json=payload)
            if res.status_code != 200:
                logging.error(f"텔레그램 응답 에러: {res.status_code} - {res.text}")
        except Exception as e:
            logging.error(f"텔레그램 API 통신 실패: {e}")

    def send_plain_message(self, message):
        """[ECO-05] 치명적 장애 발생 시 무음 실패 방지를 위한 긴급 텍스트 발송 메서드"""
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(self.base_url, json=payload)
        except Exception as e:
            logging.error(f"비상 메시지 발송 완전 실패: {e}")
