import FinanceDataReader as fdr
import pandas as pd

def test_data_source():
    sources = [
        ("KRX (한국거래소)", lambda: fdr.StockListing('KRX')),
        ("NAVER (네이버)", lambda: fdr.DataReader('005930', '2024-01-01')), # 삼성전자 샘플
        ("DAUM (다음)", lambda: fdr.DataReader('005930', '2024-01-01', exchange='DAUM'))
    ]
    
    print("📋 [공급망 가동 테스트 리포트]\n" + "="*40)
    
    for name, func in sources:
        try:
            result = func()
            if result is not None and not result.empty:
                status = "✅ 정상 (데이터 로드 성공)"
                detail = f"항목수: {len(result)}"
            else:
                status = "⚠️ 경고 (빈 데이터 반환)"
                detail = "내용 없음"
        except Exception as e:
            status = "❌ 실패 (연결 오류)"
            detail = str(e)[:50] # 에러 메시지 앞부분만
            
        print(f"📍 {name}\n   상태: {status}\n   상세: {detail}\n" + "-"*40)

if __name__ == "__main__":
    test_data_source()
