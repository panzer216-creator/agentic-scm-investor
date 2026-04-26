if __name__ == "__main__":
    logging.info("🏭 Agentic SCM Investment Engine v2.2 가동 시작")
    
    # [사전 공정 준비] 물리적 창고 부지 선확보 (Git 추적 유실 방지)
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "w", encoding="utf-8") as f:
            json.dump([], f) # 최소한의 빈 배열 주입

    fetcher = BucketFetcher()
    production_plan = fetcher.get_dynamic_production_plan()
    
    # [조달망 방어] 조달 리스트가 비어있을 경우 무음 붕괴(Silent Crash) 차단
    if not production_plan:
        logging.error("🚨 조달 실패: 분석할 종목 리스트(Production Plan)가 비어 있습니다.")
        exit(1) # 에러 코드 반환으로 Actions에 명확히 알림

    history = []
    if os.path.exists("data/analysis_history.json"):
        with open("data/analysis_history.json", "r", encoding="utf-8") as f:
            try: history = json.load(f)
            except: history = []

    kis = KISApi()
    for group_id, stocks in production_plan.items():
        for stock in stocks:
            try:
                curr_price_info = kis.get_stock_data(stock["code"])
                
                # 가동 여부 통제
                run_flag, reason, report_id = should_run_analysis(stock["code"], curr_price_info, history)
                
                if run_flag:
                    engine = AgenticSCMEngine(stock["code"], stock["name"], stock["sector"])
                    engine.run_production_line(group_id, reason, report_id)
                    time.sleep(2) # 쿨다운
                else:
                    logging.info(f"☕ {stock['name']}: {reason} (공정 스킵)")
                    
            except Exception as e:
                logging.error(f"⚠️ {stock['name']} 공정 준비 중 오류: {e}")

    logging.info("🏁 오늘의 생산 공정이 종료되었습니다.")
