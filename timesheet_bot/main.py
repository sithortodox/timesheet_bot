from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from aiohttp import web

from .api import WebAppAPI
from .config import Config
from .handlers import Handlers
from .reminders import load_reminders
from .storage import SqliteStorage

LOG_FILE = "/app/data/bot.log"


def _setup_logging() -> None:
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(), handler],
    )


def create_app(config: Config | None = None) -> Application:
    if config is None:
        config = Config.from_env()

    storage = SqliteStorage(config.db_path)
    handlers = Handlers(storage, config)

    builder = Application.builder().token(config.bot_token)
    if config.webhook_url:
        builder = builder.updater(None)
    app = builder.build()

    app.bot_data["storage"] = storage
    app.bot_data["config"] = config

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("stats", handlers.stats))
    app.add_handler(CommandHandler("week", handlers.week))
    app.add_handler(CommandHandler("projects", handlers.projects))
    app.add_handler(CommandHandler("budget", handlers.budget))
    app.add_handler(CommandHandler("salary", handlers.salary))
    app.add_handler(CommandHandler("dayoff", handlers.dayoff))
    app.add_handler(CommandHandler("team_stats", handlers.team_stats))
    app.add_handler(CommandHandler("team_export", handlers.team_export))
    app.add_handler(InlineQueryHandler(handlers.handle_inline))
    app.add_handler(ChosenInlineResultHandler(handlers.handle_chosen_inline))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handlers.handle_web_app_data)
    )
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    app.add_handler(
        MessageHandler(filters.PHOTO, handlers.handle_photo)
    )
    app.add_handler(
        MessageHandler(filters.VOICE, handlers.handle_voice)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )

    load_reminders(app, storage)

    return app


async def _webhook_handler(app: Application, api_app: web.Application, config: Config) -> None:
    webhook_path = f"/bot/{config.bot_token}"
    secret = config.webhook_secret or "SECRET"

    async def telegram_webhook(request: web.Request) -> web.Response:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            return web.json_response({"error": "unauthorized"}, status=401)
        update_data = await request.json()
        from telegram import Update as TgUpdate
        tg_update = TgUpdate.de_json(update_data, app.bot)
        if tg_update:
            app.create_task(app.process_update(tg_update))
        return web.json_response({"ok": True})

    api_app.router.add_post(webhook_path, telegram_webhook)
    await app.bot.set_webhook(
        url=f"{config.webhook_url}{webhook_path}",
        secret_token=secret,
        allowed_updates=["message", "callback_query", "inline_query", "chosen_inline_result"],
    )


async def run_bot_and_api(config: Config) -> None:
    app = create_app(config)
    storage: SqliteStorage = app.bot_data["storage"]
    api = WebAppAPI(storage, config.bot_token)

    await app.initialize()
    await app.start()

    if config.webhook_url:
        await _webhook_handler(app, api.app, config)
    else:
        await app.updater.start_polling(drop_pending_updates=True)

    runner = web.AppRunner(api.app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()

    logger = logging.getLogger(__name__)
    mode = "webhook" if config.webhook_url else "polling"
    logger.info(f"Bot + API started ({mode}, API on port 8081)")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if not config.webhook_url:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


def main() -> None:
    _setup_logging()
    config = Config.from_env()
    asyncio.run(run_bot_and_api(config))


if __name__ == "__main__":
    main()
