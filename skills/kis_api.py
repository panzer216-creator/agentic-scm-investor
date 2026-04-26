import os
import requests
import json
import time
from datetime import datetime

class KISApi:
    def __init__(self):
        self.api_key = os.getenv("KIS_API_KEY")
        self.api_secret = os.getenv("KIS_SECRET_KEY")
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None

    def get_access_token(self):
        """Mission 1: 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(payload))
        self.access_token = res.json().get("access_token")
        return self.access_token

    def is_market_open(self):
        """Mission 3-1: 국내 휴장일 여부 확인 (Gatekeeper)"""
        if not self.access_token: self.get_access_token()
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/chk-holiday"
        today = datetime.now().strftime("%Y%m%d")
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.api_key, "appsecret": self.api_secret,
            "tr_id": "CTCA0903R", "custtype": "P"
        }
        params = {"BASS_DT": today, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
        
        try:
            res = requests.get(url, headers=headers, params=params).json()
            # opnd_yn: 영업일 여부 (Y: 개장, N: 휴장)
            is_open = res['output'][0]['opnd_yn'] == 'Y'
            return is_open
        except:
            return False # 에러 시 보수적으로 휴장 판단

    def get_stock_data(self, stock_code):
        """Mission 2 & 3-2: 시세 수집 및 트래픽 통제"""
        if not self.access_token: self.get_access_token()
        
        # 트래픽 통제: KIS의 TPS 제한을 고려해 호출 전 미세한 버퍼(Buffer) 부여
        time.sleep(0.2) 
        
        price_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.api_key, "appsecret": self.api_secret,
            "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        
        try:
            res = requests.get(price_url, headers=headers, params=params).json()["output"]
            curr_p = int(res["stck_prpr"])
            high_52 = int(res["w52_hgpr"])
            return {
                "current_price": curr_p,
                "dist_from_52w_high": f"{((curr_p / high_52) - 1) * 100:.2f}%"
            }
        except:
            return None

# --- [단독 검증 모듈: M3 테스트] ---
if __name__ == "__main__":
    kis = KISApi()
    print(f"📅 오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}")
    
    # 1. 휴장일 테스트
    open_status = kis.is_market_open()
    status_msg = "🟢 개장일" if open_status else "🔴 휴장일 (공장 가동 중단 권장)"
    print(f"🚦 시장 상태: {status_msg}")
    
    # 2. 트래픽 통제 테스트 (연속 호출)
    if open_status:
        print("\n🚀 연속 데이터 호출 테스트 (Rate Limit 확인)...")
        for code in ["005930", "000660"]: # 삼성전자, SK하이닉스
            data = kis.get_stock_data(code)
            print(f"📦 종목[{code}] 데이터 수신 완료: {data['current_price']}원")
