import os
import google.generativeai as genai
from dotenv import load_dotenv

# 보안 키 불러오기
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 내 API 키로 쓸 수 있는(generateContent 지원) 모델 리스트 출력
print("📦 현재 사용 가능한 모델 목록:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")
