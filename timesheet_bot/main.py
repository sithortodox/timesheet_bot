import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import Config
from .handlers import Handlers
from .reminders import load_reminders
from .storage import SqliteStorage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def create_app(config: Config = None) -> Application:
    if config is None:
        config = Config.from_env()

    storage = SqliteStorage(config.db_path)
    handlers = Handlers(storage, config)

    app = Application.builder().token(config.bot_token).build()

    app.bot_data["storage"] = storage
    app.bot_data["config"] = config

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("stats", handlers.stats))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handlers.handle_web_app_data)
    )
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )

    load_reminders(app, storage)

    return app


def main():
    config = Config.from_env()
    app = create_app(config)
    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
