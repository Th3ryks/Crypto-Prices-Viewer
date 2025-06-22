import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from bot.handlers import router
from bot.database import init_db
from config.settings import get_token

async def main():
    load_dotenv()
    init_db()
    token = get_token()
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())