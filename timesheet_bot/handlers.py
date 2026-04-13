import csv
import io
import logging
from calendar import month_name, monthrange
from datetime import date, datetime, time

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .keyboards import (
    confirm_delete_keyboard,
    entries_keyboard,
    export_keyboard,
    main_keyboard,
    reminder_keyboard,
)
from .storage import StorageBase

logger = logging.getLogger(__name__)


class Handlers:
    def __init__(self, storage: StorageBase, config: Config):
        self.storage = storage
        self.config = config

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.storage.set_reminder(
            user.id, update.effective_chat.id, enabled=True, reminder_time="19:00"
        )
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Я помогу вести личный табель рабочего времени.\n\n"
            "📋 *Открой табель* кнопкой ниже — удобный интерфейс для записи часов и заметок.\n"
            "⏱ Или используй быстрые команды прямо здесь.\n\n"
            "_Например: отправь_ `8.5 Работал над проектом X` _— запишу на сегодня._",
            parse_mode="Markdown",
            reply_markup=main_keyboard(self.config.mini_app_url),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 *Как пользоваться:*\n\n"
            "• `8` или `8.5` — записать часы за сегодня\n"
            "• `8.5 Работал над багом` — часы + заметка\n"
            "• `7 2025-04-10` — записать за конкретную дату\n"
            "• `7.5 2025-04-10 Встречи и документация` — всё вместе\n\n"
            "📋 *Кнопка «Открыть табель»* — полный интерфейс с календарём\n"
            "📊 *Статистика* — итоги за текущий месяц\n"
            "✏️ *Редактировать* — изменить существующую запись\n"
            "🗑 *Удалить* — удалить запись\n"
            "📤 *Экспорт* — скачать CSV за месяц\n"
            "⏰ *Напоминания* — настроить напоминание записать часы",
            parse_mode="Markdown",
        )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        now = datetime.now()
        stats_data = self.storage.get_month_stats(user_id, now.year, now.month)

        if not stats_data["entries"]:
            await update.message.reply_text("📊 В этом месяце записей пока нет.")
            return

        lines = [f"📊 *Статистика за {month_name[now.month]} {now.year}*\n"]
        lines.append(f"🗓 Рабочих дней: *{stats_data['days_worked']}*")
        lines.append(f"⏱ Всего часов: *{stats_data['total_hours']:.1f}*")
        lines.append(f"📈 Среднее в день: *{stats_data['avg_hours']:.1f} ч*\n")
        lines.append("*Последние записи:*")

        for entry in stats_data["entries"][-5:]:
            note = f" — {entry['note']}" if entry.get("note") else ""
            lines.append(f"• {entry['date']}: {entry['hours']}ч{note}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        user_id = update.effective_user.id

        if context.user_data.get("edit_mode"):
            return await self._handle_edit_input(update, context)

        if text == "📊 Статистика":
            return await self.stats(update, context)
        if text == "❓ Помощь":
            return await self.help_cmd(update, context)
        if text == "⏱ Записать сегодня":
            await update.message.reply_text(
                "Отправь количество часов (можно с заметкой):\n"
                "Например: `8` или `7.5 Работал над дизайном`",
                parse_mode="Markdown",
            )
            return
        if text == "✏️ Редактировать":
            return await self._show_entries_for_edit(update, context)
        if text == "🗑 Удалить":
            return await self._show_entries_for_delete(update, context)
        if text == "📤 Экспорт":
            await update.message.reply_text(
                "📤 Выбери период для экспорта:",
                reply_markup=export_keyboard(),
            )
            return
        if text == "⏰ Напоминания":
            return await self._show_reminder_settings(update, context)

        parts = text.split(maxsplit=2)
        if not parts:
            return

        try:
            hours = float(parts[0].replace(",", "."))
        except ValueError:
            return

        if hours <= 0 or hours > 24:
            await update.message.reply_text("❌ Укажи часы от 0.5 до 24.")
            return

        date_str = date.today().isoformat()
        note = ""

        if len(parts) >= 2:
            try:
                datetime.strptime(parts[1], "%Y-%m-%d")
                date_str = parts[1]
                if len(parts) == 3:
                    note = parts[2]
            except ValueError:
                note = " ".join(parts[1:])

        self.storage.save_entry(user_id, date_str, hours, note)

        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Записано!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Часов: *{hours}*{note_text}",
            parse_mode="Markdown",
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = update.effective_user.id

        if data == "cancel":
            await query.edit_message_text("❌ Отменено.")
            return

        if data.startswith("edit:"):
            date_str = data.split(":", 1)[1]
            context.user_data["edit_mode"] = date_str
            await query.edit_message_text(
                f"✏️ Редактирование записи за *{date_str}*.\n\n"
                "Отправь новые часы (можно с заметкой):\n"
                "Например: `7.5 Обновлённая заметка`\n\n"
                "Или отправь `0` чтобы оставить только часы.",
                parse_mode="Markdown",
            )
            return

        if data.startswith("delete:"):
            date_str = data.split(":", 1)[1]
            await query.edit_message_reply_markup(
                reply_markup=confirm_delete_keyboard(date_str)
            )
            return

        if data.startswith("delete_confirm:"):
            date_str = data.split(":", 1)[1]
            deleted = self.storage.delete_entry(user_id, date_str)
            if deleted:
                await query.edit_message_text(f"🗑 Запись за *{date_str}* удалена.", parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Запись не найдена.")
            return

        if data.startswith("export:"):
            period = data.split(":", 1)[1]
            return await self._handle_export(query, user_id, period)

        if data.startswith("reminder:"):
            action = data.split(":", 1)[1]
            return await self._handle_reminder_callback(query, user_id, action)

    async def handle_web_app_data(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        import json

        raw = update.message.web_app_data.data
        user_id = update.effective_user.id
        try:
            payload = json.loads(raw)
            action = payload.get("action")

            if action == "save_entry":
                date_str = payload["date"]
                hours = float(payload["hours"])
                note = payload.get("note", "")
                self.storage.save_entry(user_id, date_str, hours, note)
                await update.message.reply_text(
                    f"✅ Сохранено из табеля!\n📅 {date_str} — {hours}ч",
                )
            elif action == "get_data":
                entries = self.storage.get_entries(user_id)
                await update.message.reply_text(
                    f"📊 Данные синхронизированы ({len(entries)} записей)",
                )
        except Exception as e:
            logger.error(f"Web app data error: {e}")

    async def _show_entries_for_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        entries = self.storage.get_entries(update.effective_user.id, limit=10)
        if not entries:
            await update.message.reply_text("✏️ Записей для редактирования нет.")
            return
        kb = entries_keyboard(entries, "edit")
        await update.message.reply_text(
            "✏️ Выбери запись для редактирования:", reply_markup=kb
        )

    async def _show_entries_for_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        entries = self.storage.get_entries(update.effective_user.id, limit=10)
        if not entries:
            await update.message.reply_text("🗑 Записей для удаления нет.")
            return
        kb = entries_keyboard(entries, "delete")
        await update.message.reply_text(
            "🗑 Выбери запись для удаления:", reply_markup=kb
        )

    async def _handle_edit_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        date_str = context.user_data.pop("edit_mode")
        user_id = update.effective_user.id
        text = update.message.text.strip()

        try:
            hours = float(text.replace(",", ".").split(maxsplit=1)[0])
        except ValueError:
            context.user_data["edit_mode"] = date_str
            await update.message.reply_text("❌ Отправь число (часы).")
            return

        if hours <= 0 or hours > 24:
            context.user_data["edit_mode"] = date_str
            await update.message.reply_text("❌ Укажи часы от 0.5 до 24.")
            return

        parts = text.split(maxsplit=1)
        note = parts[1] if len(parts) > 1 else ""
        self.storage.save_entry(user_id, date_str, hours, note)

        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Запись обновлена!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Часов: *{hours}*{note_text}",
            parse_mode="Markdown",
        )

    async def _handle_export(self, query, user_id: int, period: str):
        now = datetime.now()
        if period == "current":
            year, month = now.year, now.month
        elif period == "prev":
            year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        else:
            await query.edit_message_text("❌ Неизвестный период.")
            return

        stats_data = self.storage.get_month_stats(user_id, year, month)
        if not stats_data["entries"]:
            await query.edit_message_text("📊 За этот период записей нет.")
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Дата", "Часы", "Заметка", "Обновлено"])
        for entry in stats_data["entries"]:
            writer.writerow(
                [entry["date"], entry["hours"], entry.get("note", ""), entry.get("updated_at", "")]
            )

        csv_bytes = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        csv_bytes.name = f"timesheet_{year}-{month:02d}.csv"

        await query.edit_message_text(f"📤 Экспорт за {month_name[month]} {year}:")
        await query.message.reply_document(csv_bytes)

    async def _show_reminder_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        reminder = self.storage.get_reminder(user_id)
        enabled = reminder["enabled"] if reminder else False
        r_time = reminder["reminder_time"] if reminder else "19:00"

        status = "🟢 Включены" if enabled else "🔴 Выключены"
        text = (
            f"⏰ *Напоминания*\n\n"
            f"Статус: {status}\n"
            f"Время: *{r_time}*\n\n"
            f"Бот напомнит записать часы, если ты ещё не внёс запись за день."
        )
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reminder_keyboard(enabled)
        )

    async def _handle_reminder_callback(self, query, user_id: int, action: str):
        chat_id = query.message.chat.id

        if action == "toggle":
            reminder = self.storage.get_reminder(user_id)
            was_enabled = reminder["enabled"] if reminder else False
            new_enabled = not was_enabled
            r_time = reminder["reminder_time"] if reminder else "19:00"
            self.storage.set_reminder(user_id, chat_id, new_enabled, r_time)

            status = "🟢 Включены" if new_enabled else "🔴 Выключены"
            await query.edit_message_text(
                f"⏰ Напоминания {status}.\nВремя: *{r_time}*",
                parse_mode="Markdown",
            )
        elif action == "time":
            self.storage.set_reminder(user_id, chat_id, True, "19:00")
            await query.edit_message_text(
                "🕐 Отправь новое время напоминания в формате ЧЧ:ММ\n"
                "Например: `18:30` или `20:00`",
                parse_mode="Markdown",
            )
