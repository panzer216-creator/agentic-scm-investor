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
        """[공정 0] 토큰 발급 및 캐싱 (발급된 토큰이 있으면 재사용)"""
        if self.access_token:
            return self.access_token

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        try:
            res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(payload))
            self.access_token = res.json().get("access_token")
            return self.access_token
        except Exception as e:
            logging.error(f"토큰 발급 실패: {e}")
            return None

    def is_market_open(self):
        """[Gatekeeper] 국내 휴장일 여부 확인 (영업일이면 True, 휴일이면 False)"""
        token = self.get_access_token()
        if not token: return False
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/chk-holiday"
        today = datetime.now().strftime("%Y%m%d")
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.api_key, "appsecret": self.api_secret,
            "tr_id": "CTCA0903R", "custtype": "P"
        }
        params = {"BASS_DT": today, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
        
        try:
            res = requests.get(url, headers=headers, params=params).json()
            # opnd_yn: 영업일 여부 (Y: 개장, N: 휴장)
            return res.get('output', [{}])[0].get('opnd_yn') == 'Y'
        except Exception as e:
            logging.warning(f"휴장일 확인 실패({e}): 보수적 관점에서 휴장으로 판단")
            return False

    def get_stock_data(self, stock_code):
        """[Sourcing] 주가 및 52주 최고가 수집 (트래픽 통제 포함)"""
        token = self.get_access_token()
        if not token: return None
        
        # KIS TPS(초당 호출 제한) 대응을 위한 미세 버퍼
        time.sleep(0.2) 
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.api_key, "appsecret": self.api_secret,
            "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        
        try:
            res = requests.get(url, headers=headers, params=params).json().get("output")
            if not res: return None
            
            curr_p = int(res["stck_prpr"])
            high_52 = int(res["w52_hgpr"])
            
            return {
                "current_price": curr_p,
                "dist_from_52w_high": f"{((curr_p / high_52) - 1) * 100:.2f}%"
            }
        except Exception as e:
            logging.error(f"주가 수집 실패({stock_code}): {e}")
            return None

# --- [단독 검증 모듈] ---
if __name__ == "__main__":
    kis = KISApi()
    print(f"🔍 검증 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 공정 1: 휴장일 체크
    if kis.is_market_open():
        print("🚦 시장 상태: 🟢 개장일 (분석 프로세스 가동)")
        # 공정 2: 샘플 종목 수집 테스트
        for code in ["005930", "000660"]:
            data = kis.get_stock_data(code)
            print(f"📦 종목[{code}] 데이터: {data}")
    else:
        print("🚦 시장 상태: 🔴 휴장일 (데이터 공급망 일시 정지)")
