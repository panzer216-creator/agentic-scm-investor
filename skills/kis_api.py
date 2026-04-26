import os
import requests
import json

class KISApi:
    def __init__(self):
        # GHA Secrets에서 환경 변수 로드
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
                data = response.json()
                self.access_token = data.get("access_token")
                return self.access_token
            else:
                print(f"❌ 토큰 발급 실패: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"⚠️ 연결 에러 발생: {e}")
            return None

# --- [단독 검증 모듈: M1 테스트] ---
if __name__ == "__main__":
    # 이 파일만 단독 실행했을 때 작동하는 테스트 로직
    print("🚀 [M1] KIS 인증 테스트 시작...")
    
    kis = KISApi()
    token = kis.get_access_token()
    
    if token:
        print(f"✅ 인증 성공! 토큰 확보 완료 (길이: {len(token)})")
        print(f"💡 토큰 앞부분 확인: {token[:10]}...")
    else:
        print("❌ 인증 실패. Secrets 설정이나 API 키를 확인하세요.")

