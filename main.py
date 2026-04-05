import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN, GROUP_ID, ADMIN_IDS
from database import init_db, get_ticket, close_ticket, get_active_tickets
from handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

scheduler = AsyncIOScheduler()

from datetime import datetime, timezone   

async def check_timeouts():
    tickets = await get_active_tickets()
    now = datetime.now(timezone.utc)       
    for t in tickets:
        user_id = t[0]
        ticket = await get_ticket(user_id)
        if ticket:
            last_str = ticket[6]
            try:
                last_activity = datetime.strptime(last_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
                
            delta = now - last_activity.replace(tzinfo=timezone.utc)  
            if delta > timedelta(hours=1):
                await close_ticket(user_id, bot, GROUP_ID, "таймаут (1 час без активности)")

async def on_startup():
    await init_db()
    scheduler.add_job(check_timeouts, "interval", minutes=1)
    scheduler.start()
    logging.info("Бот запущен")
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, "Бот поддержки запущен!")

async def main():
    dp.include_router(router)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())