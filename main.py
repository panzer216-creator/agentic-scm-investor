import FinanceDataReader as fdr
import pandas as pd

def audit_data_sources():
    test_symbol = '005930' # 삼성전자
    print(f"🔍 [공급망 전수 조사 시작 - {test_symbol}]")
    print("="*50)

    # 1. 종목 리스트(Listing) 공급처 테스트
    listing_sources = ['KRX', 'KOSPI', 'KOSDAQ', 'NASDAQ']
    for src in listing_sources:
        try:
            df = fdr.StockListing(src)
            status = f"✅ 성공 (항목수: {len(df)})" if not df.empty else "⚠️ 빈 데이터"
            print(f"📍 StockListing('{src}'): {status}")
        except Exception as e:
            print(f"❌ StockListing('{src}'): 실패 (에러: {str(e)[:50]})")

    print("-" * 50)

    # 2. 개별 주가(Price) 공급처 테스트
    # FinanceDataReader는 기본적으로 Naver/Daum 등을 내부적으로 선택합니다.
    price_tests = [
        ("기본 DataReader", lambda: fdr.DataReader(test_symbol)),
        ("Naver 소스", lambda: fdr.DataReader(test_symbol, exchange='KRX')), # fdr의 KRX는 보통 Naver 기반
        ("Daum 소스", lambda: fdr.DataReader(test_symbol, exchange='DAUM'))
    ]

    for name, func in price_tests:
        try:
            df = func()
            status = f"✅ 성공 (최근 종가: {df['Close'].iloc[-1]})" if not df.empty else "⚠️ 빈 데이터"
            print(f"📍 {name}: {status}")
        except Exception as e:
            print(f"❌ {name}: 실패 (에러: {str(e)[:50]})")

if __name__ == "__main__":
    audit_data_sources()
