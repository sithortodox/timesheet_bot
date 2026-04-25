import logging
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .keyboards import main_keyboard
from .storage import StorageBase

logger = logging.getLogger(__name__)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    storage: StorageBase = context.bot_data["storage"]
    config = context.bot_data["config"]
    today_str = date.today().isoformat()

    users = storage.get_users_without_entry(today_str)
    now = datetime.now().strftime("%H:%M")

    for user in users:
        reminder_time = user["reminder_time"]
        if now != reminder_time:
            continue

        try:
            await context.bot.send_message(
                chat_id=user["chat_id"],
                text=(
                    "⏰ *Напоминание!*\n\n"
                    "Ты ещё не записал часы за сегодня.\n"
                    "Отправь начало и конец смены: `09:00 18:00`"
                ),
                parse_mode="Markdown",
                reply_markup=main_keyboard(config.mini_app_url, user_id=user["user_id"]),
            )
            storage.mark_reminder_sent(user["user_id"], today_str)
            logger.info(f"Reminder sent to user {user['user_id']}")
        except Exception as e:
            logger.error(f"Failed to send reminder to {user['user_id']}: {e}")


async def check_yesterday_reminder(context: ContextTypes.DEFAULT_TYPE):
    storage: StorageBase = context.bot_data["storage"]
    config = context.bot_data["config"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    now = datetime.now().strftime("%H:%M")

    if now != "09:00":
        return

    all_reminders = storage.get_all_reminders()
    for user in all_reminders:
        if not user.get("enabled"):
            continue
        user_id = user["user_id"]
        chat_id = user["chat_id"]
        entries = storage.get_entries(user_id, date_from=yesterday, date_to=yesterday)
        if entries:
            continue
        if storage.is_reminder_sent(user_id, yesterday):
            continue

        try:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("09:00-18:00", callback_data=f"yesterday:09:00:18:00:{yesterday}"),
                    InlineKeyboardButton("08:00-17:00", callback_data=f"yesterday:08:00:17:00:{yesterday}"),
                ],
                [
                    InlineKeyboardButton("🛌 Выходной", callback_data=f"yesterday:dayoff:{yesterday}"),
                    InlineKeyboardButton("❌ Пропустить", callback_data="cancel"),
                ],
            ])
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"☀️ *Доброе утро!*\n\n"
                    f"За вчера (*{yesterday}*) нет записи.\n"
                    f"Записать смену?"
                ),
                parse_mode="Markdown",
                reply_markup=kb,
            )
            storage.mark_reminder_sent(user_id, yesterday)
            logger.info(f"Yesterday reminder sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send yesterday reminder to {user_id}: {e}")


def load_reminders(app, storage: StorageBase):
    from .config import Config

    config: Config = app.bot_data["config"]
    app.job_queue.run_repeating(
        check_reminders,
        interval=config.reminder_check_interval,
        first=1,
        name="reminder_check",
    )
    app.job_queue.run_repeating(
        check_yesterday_reminder,
        interval=60,
        first=5,
        name="yesterday_reminder",
    )
    logger.info("Reminder jobs scheduled")
