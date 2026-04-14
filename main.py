import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- [1. Configuration] ---
SHEET_ID = '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0'
MASTER_TAB = "Seed_Data_414" 
KEEPLIST = [MASTER_TAB, "Trading_Log"] # 삭제하지 않고 유지할 핵심 탭

# --- [2. 마스터 데이터 리스트 (지수 제외, 섹터 특화형)] ---
MASTER_DATA = [
    ["Category", "Stock Name", "Ticker"],
    # [전략 섹터 ETF - 산업군의 온도계]
    ["전략 ETF", "KODEX 반도체", "091160"],
    ["전략 ETF", "KODEX 바이오", "244580"],
    ["전략 ETF", "KODEX K-뷰티", "483320"],
    ["전략 ETF", "TIGER 로봇TOP10", "440420"],
    ["전략 ETF", "TIGER 2차전지테마", "305540"],
    ["전략 ETF", "TIGER 현대차그룹+", "138540"],
    ["전략 ETF", "KODEX 삼성그룹", "102770"],
    ["전략 ETF", "KODEX 조선", "102960"],
    ["전략 ETF", "TIGER 우주방산", "457190"],
    ["전략 ETF", "KODEX AI전력핵심설비", "487240"],
    
    # [산업군별 핵심 대장주 - 사용자님 관심 종목 및 히트맵 분석 반영]
    ["반도체/HBM", "삼성전자", "005930"],
    ["반도체/HBM", "SK하이닉스", "000660"],
    ["반도체/HBM", "한미반도체", "042700"],
    ["반도체/HBM", "리노공업", "058470"],
    ["제약/바이오", "삼성바이오로직스", "207940"],
    ["제약/바이오", "셀트리온", "068270"],
    ["제약/바이오", "유한양행", "000100"],
    ["제약/바이오", "리가켐바이오", "141080"],
    ["K-뷰티", "아모레퍼시픽", "090430"],
    ["K-뷰티", "실리콘투", "257720"],
    ["K-뷰티", "코스메카코리아", "242410"],
    ["K-뷰티", "브이티", "018290"],
    ["로봇/AI", "레인보우로보틱스", "277810"],
    ["로봇/AI", "두산로보틱스", "454910"],
    ["자동차", "현대차", "005380"],
    ["자동차", "기아", "000270"],
    ["전력/에너지", "HD현대일렉트릭", "267260"],
    ["전력/에너지", "효성중공업", "298040"],
    ["전력/에너지", "LS ELECTRIC", "010120"],
    ["방산/우주", "한화에어로스페이스", "012450"],
    ["방산/우주", "현대로템", "064350"],
    ["방산/우주", "LIG넥스원", "079550"],
    ["조선", "HD현대중공업", "329180"],
    ["조선", "한화오션", "042660"],
    ["조선", "삼성중공업", "010140"]
]

def cleanup_and_setup_sheet():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds).spreadsheets()

    # 1. 기존 시트 확인 및 불필요한 탭 삭제
    spreadsheet = service.get(spreadsheetId=SHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])
    
    delete_requests = []
    for s in sheets:
        title = s['properties']['title']
        if title not in KEEPLIST:
            delete_requests.append({'deleteSheet': {'sheetId': s['properties']['sheetId']}})
    
    if delete_requests:
        service.batchUpdate(spreadsheetId=SHEET_ID, body={'requests': delete_requests}).execute()
        print(f"🧹 불필요한 탭 {len(delete_requests)}개 정리 완료.")

    # 2. MASTER_TAB이 없으면 생성
    sheet_names = [s['properties']['title'] for s in sheets]
    if MASTER_TAB not in sheet_names:
        service.batchUpdate(spreadsheetId=SHEET_ID, body={'requests': [{'addSheet': {'properties': {'title': MASTER_TAB}}}]}).execute()

    # 3. 데이터 기록 (초기 자재 입고)
    service.values().clear(spreadsheetId=SHEET_ID, range=f"'{MASTER_TAB}'!A:C").execute()
    service.values().update(
        spreadsheetId=SHEET_ID, 
        range=f"'{MASTER_TAB}'!A1", 
        valueInputOption="RAW", 
        body={"values": MASTER_DATA}
    ).execute()
    
    print(f"✅ 마스터 데이터 입고 완료: {len(MASTER_DATA)-1}개의 전략 자산 등록.")

if __name__ == "__main__":
    cleanup_and_setup_sheet()
