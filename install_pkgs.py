import subprocess
import sys

# 설치할 패키지 명단
packages = [
    "finance-datareader",
    "pandas"
]

print("📦 패키지 설치를 시작합니다...")

for pkg in packages:
    print(f"--- {pkg} 설치 중 ---")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

print("✅ 모든 패키지가 성공적으로 설치되었습니다!")
