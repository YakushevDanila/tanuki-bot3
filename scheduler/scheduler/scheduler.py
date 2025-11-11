from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import pytz
from config import TIMEZONE, ALLOWED_USER_ID
import sheets

async def send_shift_reminder(bot):
    """Напоминание о смене в 10:00"""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).strftime("%d.%m.%Y")

    if sheets.has_shift_today(today):
        await bot.send_message(
            ALLOWED_USER_ID,
            f"🌞 Доброе утро, Аня!\n"
            f"Сегодня у тебя смена ({today}) 💪\n"
            f"Не забудь взять хорошее настроение и кофеек ☕️"
        )


async def send_evening_prompt(bot):
    """Напоминание вечером в день смены"""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).strftime("%d.%m.%Y")

    if sheets.has_shift_today(today):
        await bot.send_message(
            ALLOWED_USER_ID,
            f"🌙 Привет, Аня!\n"
            f"Смена {today} подошла к концу(или скоро подойдет) 💫\n"
            f"Пожалуйста, введи данные за день — выручку и чай ☕️💰\n"
            f"Используй команды:\n"
            f"→ /выручка — чтобы ввести выручку\n"
            f"→ /чай — чтобы ввести сумму чая"
        )


def setup_scheduler(bot):
    tz = pytz.timezone(TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    # 10:00 МСК — напоминание о смене
    scheduler.add_job(send_shift_reminder, "cron", hour=10, minute=0, args=[bot])

    # 22:00 МСК — напоминание ввести данные
    scheduler.add_job(send_evening_prompt, "cron", hour=22, minute=0, args=[bot])

    scheduler.start()
