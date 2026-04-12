"""
Telegram Timesheet Bot
Запуск: python bot.py
Требования: pip install python-telegram-bot==20.7
"""

import os
import json
import logging
from datetime import datetime, date
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Конфиг ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-domain.com/miniapp/index.html")

# ── Хранилище (JSON-файл, для прода — замени на БД) ──────────────────────────
DATA_FILE = os.getenv("DATA_FILE", "timesheet_data.json")

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id: int) -> dict:
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"entries": {}}
        save_data(data)
    return data[uid]

def save_entry(user_id: int, date_str: str, hours: float, note: str = ""):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"entries": {}}
    data[uid]["entries"][date_str] = {
        "hours": hours,
        "note": note,
        "updated_at": datetime.now().isoformat()
    }
    save_data(data)

# ── Клавиатура главного меню ──────────────────────────────────────────────────
def main_keyboard(mini_app_url: str):
    keyboard = [
        [KeyboardButton("📋 Открыть табель", web_app=WebAppInfo(url=mini_app_url))],
        [KeyboardButton("⏱ Записать сегодня"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ── Хэндлеры ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я помогу вести личный табель рабочего времени.\n\n"
        "📋 *Открой табель* кнопкой ниже — там удобный интерфейс для записи часов и заметок.\n"
        "⏱ Или используй быстрые команды прямо здесь.\n\n"
        "_Например: отправь_ `8.5 Работал над проектом X` _— запишу на сегодня._",
        parse_mode="Markdown",
        reply_markup=main_keyboard(MINI_APP_URL),
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Как пользоваться:*\n\n"
        "• `8` или `8.5` — записать часы за сегодня\n"
        "• `8.5 Работал над багом` — часы + заметка\n"
        "• `7 2025-04-10` — записать за конкретную дату\n"
        "• `7.5 2025-04-10 Встречи и документация` — всё вместе\n\n"
        "📋 *Кнопка «Открыть табель»* — полный интерфейс с календарём\n"
        "📊 *Статистика* — итоги за текущий месяц",
        parse_mode="Markdown",
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    entries = user_data.get("entries", {})

    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    month_entries = {k: v for k, v in entries.items() if k.startswith(month_prefix)}

    if not month_entries:
        await update.message.reply_text("📊 В этом месяце записей пока нет.")
        return

    total_hours = sum(e["hours"] for e in month_entries.values())
    days_worked = len(month_entries)
    avg_hours = total_hours / days_worked if days_worked else 0

    lines = [f"📊 *Статистика за {now.strftime('%B %Y')}*\n"]
    lines.append(f"🗓 Рабочих дней: *{days_worked}*")
    lines.append(f"⏱ Всего часов: *{total_hours:.1f}*")
    lines.append(f"📈 Среднее в день: *{avg_hours:.1f} ч*\n")
    lines.append("*Последние записи:*")

    sorted_entries = sorted(month_entries.items(), reverse=True)[:5]
    for date_str, entry in sorted_entries:
        note = f" — {entry['note']}" if entry.get("note") else ""
        lines.append(f"• {date_str}: {entry['hours']}ч{note}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Кнопки меню
    if text == "📊 Статистика":
        await stats(update, context)
        return
    if text == "❓ Помощь":
        await help_cmd(update, context)
        return
    if text == "⏱ Записать сегодня":
        await update.message.reply_text(
            "Отправь количество часов (можно с заметкой):\n"
            "Например: `8` или `7.5 Работал над дизайном`",
            parse_mode="Markdown"
        )
        return

    # Парсинг быстрой записи
    # Форматы: "8", "8.5", "8.5 Заметка", "8.5 2025-04-10", "8.5 2025-04-10 Заметка"
    parts = text.split(maxsplit=2)
    if not parts:
        return

    try:
        hours = float(parts[0].replace(",", "."))
    except ValueError:
        return  # не наша команда

    if hours <= 0 or hours > 24:
        await update.message.reply_text("❌ Укажи часы от 0.5 до 24.")
        return

    date_str = date.today().isoformat()
    note = ""

    if len(parts) >= 2:
        # Проверяем, дата ли это
        try:
            datetime.strptime(parts[1], "%Y-%m-%d")
            date_str = parts[1]
            if len(parts) == 3:
                note = parts[2]
        except ValueError:
            # Не дата — значит заметка
            note = " ".join(parts[1:])

    save_entry(user_id, date_str, hours, note)

    note_text = f"\n📝 Заметка: _{note}_" if note else ""
    await update.message.reply_text(
        f"✅ Записано!\n"
        f"📅 Дата: *{date_str}*\n"
        f"⏱ Часов: *{hours}*{note_text}",
        parse_mode="Markdown"
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем данные из Mini App (когда Mini App шлёт sendData)."""
    data = update.message.web_app_data.data
    user_id = update.effective_user.id
    try:
        payload = json.loads(data)
        action = payload.get("action")

        if action == "save_entry":
            date_str = payload["date"]
            hours = float(payload["hours"])
            note = payload.get("note", "")
            save_entry(user_id, date_str, hours, note)
            await update.message.reply_text(
                f"✅ Сохранено из табеля!\n📅 {date_str} — {hours}ч",
            )
        elif action == "get_data":
            # Mini App запрашивает все данные пользователя
            user_data = get_user_data(user_id)
            await update.message.reply_text(
                f"📊 Данные синхронизированы ({len(user_data['entries'])} записей)",
            )
    except Exception as e:
        logger.error(f"Web app data error: {e}")

# ── Webhook endpoint для получения данных из Mini App через API ───────────────
# В проде лучше использовать отдельный FastAPI/Flask сервер
# и хранить данные в БД (PostgreSQL, SQLite)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
