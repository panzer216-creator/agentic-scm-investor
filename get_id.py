import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

async def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = Bot(token=token)
    
    print("🔎 최신 메시지에서 Chat ID를 찾는 중...")
    updates = await bot.get_updates()
    
    if not updates:
        print("❌ 최근에 봇에게 보낸 메시지가 없습니다.")
        print("💡 텔레그램 앱에서 봇에게 '안녕'이라고 아무 메시지나 보낸 뒤 다시 실행하세요.")
        return

    # 가장 최근 메시지를 보낸 사용자의 ID 출력
    last_update = updates[-1]
    chat_id = last_update.message.chat.id
    user_name = last_update.message.from_user.first_name
    
    print("-" * 30)
    print(f"✅ 사용자 이름: {user_name}")
    print(f"📌 당신의 Chat ID: {chat_id}")
    print("-" * 30)
    print("위 숫자를 따로 메모해 두세요. 자동 배달 시스템의 핵심 주소입니다.")

if __name__ == "__main__":
    asyncio.run(main())
