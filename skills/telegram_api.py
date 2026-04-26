import os
import requests
import logging

class TelegramApi:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_report(self, stock_name, decision):
        # 메시지 구성 로직 (기존과 동일)
        text = f"🏆 [투자 전략 리포트: {stock_name}]\n..." 
        
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}

        try:
            res = requests.post(self.base_url, json=payload)
            # [보완] 텔레그램 서버의 실제 응답 확인
            if res.status_code != 200:
                logging.error(f"❌ 텔레그램 서버 응답 에러: {res.status_code} - {res.text}")
                return False
            return True
        except Exception as e:
            logging.error(f"❌ 텔레그램 통신 실패: {e}")
            return False
