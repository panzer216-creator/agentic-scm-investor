def should_run_analysis(stock_code, current_price_data, last_history_list):
    """
    [SCM 지능형 제어] 불필요한 분석 공정 생략 판단
    """
    # 1. 해당 종목의 마지막 분석 기록 추출
    target_history = [h for h in last_history_list if h.get('stock_code') == stock_code]
    if not target_history:
        return True, "신규 종목 분석" # 첫 분석은 무조건 실행

    last_record = target_history[-1]
    
    # 2. 공시 변동 체크 (DART API 활용)
    current_report_id = DartApi().get_latest_report_id(stock_code)
    last_report_id = last_record.get("data_fingerprint")
    
    if current_report_id != last_report_id:
        return True, f"신규 공시 감지 ({current_report_id})"

    # 3. 주가 변동성 트리거 (±5% 이상 변동 시 공시와 무관하게 재분석)
    # last_record에 저장해둔 분석 시점 가격과 현재가 비교
    last_price = last_record.get("ui_metrics", {}).get("last_analyzed_price", 0)
    current_price = current_price_data.get("current_price", 0)
    
    if last_price > 0:
        change_rate = abs((current_price - last_price) / last_price) * 100
        if change_rate >= 5.0:
            return True, f"주가 급변 감지 ({change_rate:.1f}%)"

    return False, "변동 사항 없음"

# 메인 루프 예시
# for stock in production_plan:
#     run_flag, reason = should_run_analysis(stock['code'], current_price, history)
#     if run_flag:
#         engine.run_production_line(group_id, reason)
