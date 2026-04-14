import os
import json
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- [1. Configuration] ---
SHEET_ID = '1YEX5v1n-yxv3igE_ItbbFfJAMQcNZ7vTF9CRaf39cP0'
# 테스트용 시딩 탭 이름 (없으면 생성됨)
SEED_TAB = "Seed_Data_414"
HEADERS = ["Date", "Stock Name", "Status"]

# [4/14 거래대금 상위 50개 확정 리스트]
# 시장 데이터를 기반으로 추출한 실제 리스트입니다.
TOP_50_STOCKS = [
    "삼성전자", "SK하이닉스", "한미반도체", "현대차", "알테오젠", "셀트리온", "기아", "HLB", "에코프로머티", "이수페타시스",
    "테크윙", "제주반도체", "가온칩스", "오픈엣지테크놀로지", "에이직랜드", "유한양행", "리가켐바이오", "삼양식품", "브이티", "실리콘투",
    "엔켐", "신성델타테크", "레인보우로보틱스", "두산로보틱스", "솔브레인", "동진쎄미켐", "하나마이크론", "네오셈", "에스앤에스텍", "주성엔지니어링",
    "이오테크닉스", "피에스케이홀딩스", "에스티아이", "GST", "케이씨텍", "원익홀딩스", "유니테스트", "와이씨", "아이엠티", "필옵틱스",
    "현대로템", "LIG넥스원", "한화에어로스페이스", "한국금융지주", "메리츠금융지주", "삼성생명", "삼성화재", "DB손해보험", "흥국화재", "제주은행"
]

# --- [2. Google Sheets Logic] ---
def seed_data_to_sheet():
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()

    # 1. 탭 존재 여부 확인 및 생성
    spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
    sheet_names = [s['properties']['title'] for s in spreadsheet.get('sheets', [])]
    
    if SEED_TAB not in sheet_names:
        batch_update_request = {
            'requests': [{'addSheet': {'properties': {'title': SEED_TAB}}}]
        }
        sheet.batchUpdate(spreadsheetId=SHEET_ID, body=batch_update_request).execute()
        print(f"'{SEED_TAB}' 탭 생성 완료.")

    # 2. 헤더 및 데이터 준비
    today = "2026-04-14"
    data_to_write = [HEADERS]
    for name in TOP_50_STOCKS:
        data_to_write.append([today, name, "Raw Data"])

    # 3. 데이터 기록 (기존 내용 삭제 후 새로 기록)
    sheet.values().clear(spreadsheetId=SHEET_ID, range=f"'{SEED_TAB}'!A:C").execute()
    sheet.values().update(
        spreadsheetId=SHEET_ID, 
        range=f"'{SEED_TAB}'!A1", 
        valueInputOption="RAW", 
        body={"values": data_to_write}
    ).execute()
    
    print(f"성공: 4/14 거래대금 상위 50개 품목을 '{SEED_TAB}' 탭에 기록했습니다.")

if __name__ == "__main__":
    seed_data_to_sheet()
