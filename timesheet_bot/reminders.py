import logging
from datetime import date, datetime, time

from telegram.ext import ContextTypes

from .storage import StorageBase

logger = logging.getLogger(__name__)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    storage: StorageBase = context.bot_data["storage"]
    today = date.today().isoformat()

    users = storage.get_users_without_entry(today)
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
                    "Отправь количество часов, например: `8` или `7.5 Работал над проектом`",
                    parse_mode="Markdown",
                ),
            )
            storage.mark_reminder_sent(user["user_id"], today)
            logger.info(f"Reminder sent to user {user['user_id']}")
        except Exception as e:
            logger.error(f"Failed to send reminder to {user['user_id']}: {e}")


def load_reminders(app, storage: StorageBase):
    from .config import Config

    config: Config = app.bot_data["config"]
    app.job_queue.run_repeating(
        check_reminders,
        interval=config.reminder_check_interval,
        first=1,
        name="reminder_check",
    )
    logger.info("Reminder job scheduled")
