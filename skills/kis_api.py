import os
import requests
import json
import time
from datetime import datetime
import logging

class KISApi:
    def __init__(self):
        self.api_key = os.getenv("KIS_API_KEY")
        self.api_secret = os.getenv("KIS_SECRET_KEY")
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None

    def get_access_token(self):
        """[검증 완료] 토큰 캐싱 로직 추가로 중복 호출 방지"""
        if self.access_token: return self.access_token
        
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {"grant_type": "client_credentials", "appkey": self.api_key, "appsecret": self.api_secret}
        try:
            res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(payload))
            self.access_token = res.json().get("access_token")
            return self.access_token
        except: return None

    def is_market_open(self):
        """국내 휴장일 확인 (Gatekeeper)"""
        token = self.get_access_token()
        if not token: return False
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/chk-holiday"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.api_key, "appsecret": self.api_secret, "tr_id": "CTCA0903R", "custtype": "P"
        }
        params = {"BASS_DT": datetime.now().strftime("%Y%m%d"), "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
        
        try:
            res = requests.get(url, headers=headers, params=params).json()
            return res['output'][0]['opnd_yn'] == 'Y'
        except: return False

    def get_stock_data(self, stock_code):
        """시세 및 52주 최고가 수집"""
        token = self.get_access_token()
        if not token: return None
        
        time.sleep(0.2) # 트래픽 통제
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json", "authorization": f"Bearer {token}",
            "appkey": self.api_key, "appsecret": self.api_secret, "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        
        try:
            res = requests.get(url, headers=headers, params=params).json()["output"]
            curr_p = int(res["stck_prpr"])
            high_52 = int(res["w52_hgpr"])
            return {"current_price": curr_p, "dist_from_52w_high": f"{((curr_p / high_52) - 1) * 100:.2f}%"}
        except: return None

if __name__ == "__main__":
    kis = KISApi()
    if kis.is_market_open():
        print(f"🟢 개장일: {kis.get_stock_data('005930')}")
    else:
        print("🔴 휴장일")
