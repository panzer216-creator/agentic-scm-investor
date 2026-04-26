import os
import requests
import json
import time

class KISApi:
    def __init__(self):
        self.api_key = os.getenv("KIS_API_KEY")
        self.api_secret = os.getenv("KIS_SECRET_KEY")
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None

    def get_access_token(self):
        """Mission 1: KIS OAuth2 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                self.access_token = response.json().get("access_token")
                return self.access_token
            return None
        except Exception as e:
            print(f"⚠️ 인증 에러: {e}")
            return None

    def get_stock_data(self, stock_code):
        """Mission 2: 국내주식 현재가 및 수급 데이터 통합 수집"""
        if not self.access_token:
            self.get_access_token()

        # 1. 현재가 및 52주 신고가 정보 조회
        price_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        price_headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.api_key,
            "appsecret": self.api_secret,
            "tr_id": "FHKST01010100"
        }
        price_params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
        
        # 2. 투자자별 매매동향(수급) 조회
        investor_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        investor_headers = price_headers.copy()
        investor_headers["tr_id"] = "FHKST01010900"

        try:
            # 시세 데이터 처리
            res_p = requests.get(price_url, headers=price_headers, params=price_params).json()["output"]
            curr_price = int(res_p["stck_prpr"])
            high_52w = int(res_p["w52_hgpr"])
            
            # 수급 데이터 처리 (최근 5거래일 합산)
            res_i = requests.get(investor_url, headers=investor_headers, params=price_params).json()["output"]
            foreign_5d = sum(int(day["frgn_ntby_qty"]) for day in res_i[:5])
            inst_5d = sum(int(day["orgn_ntby_qty"]) for day in res_i[:5])

            # 통합 스키마 리턴
            return {
                "price_info": {
                    "current_price": curr_price,
                    "change_rate": float(res_p["prdy_ctrt"]),
                    "dist_from_52w_high": f"{((curr_price / high_52w) - 1) * 100:.2f}%"
                },
                "supply_demand": {
                    "foreign_net_buy_5d": foreign_5d,
                    "inst_net_buy_5d": inst_5d
                }
            }
        except Exception as e:
            print(f"❌ 데이터 수집 중 에러: {e}")
            return None

# --- [단독 검증 모듈: M2 테스트] ---
if __name__ == "__main__":
    print("🚀 [M2] 데이터 수집 테스트 시작 (대상: 삼성전자)...")
    kis = KISApi()
    data = kis.get_stock_data("005930")
    
    if data:
        print("\n✅ 데이터 수집 성공!")
        print(f"📊 [시세] 현재가: {data['price_info']['current_price']}원 ({data['price_info']['change_rate']}%)")
        print(f"📉 [위치] 52주 고점 대비: {data['price_info']['dist_from_52w_high']}")
        print(f"🏢 [수급] 5일 누적 - 외인: {data['supply_demand']['foreign_net_buy_5d']} / 기관: {data['supply_demand']['inst_net_buy_5d']}")
    else:
        print("❌ 데이터 수집 실패.")
