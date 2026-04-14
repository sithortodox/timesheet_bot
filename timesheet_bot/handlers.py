from __future__ import annotations

import csv
import io
import logging
from calendar import month_name, monthrange as _monthrange
from datetime import date as date_type, datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .keyboards import (
    confirm_delete_keyboard,
    entries_keyboard,
    export_keyboard,
    main_keyboard,
    project_keyboard,
    reminder_keyboard,
    week_keyboard,
)
from .storage import StorageBase
from .utils import (
    RateLimiter,
    format_entry_line,
    format_stats_header,
    parse_project,
)

logger = logging.getLogger(__name__)

_rate_limiter = RateLimiter(max_calls=20, period=60)


def _week_range(d: date_type) -> tuple[date_type, date_type]:
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


class Handlers:
    def __init__(self, storage: StorageBase, config: Config) -> None:
        self.storage = storage
        self.config = config

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        self.storage.set_reminder(
            user.id, update.effective_chat.id, enabled=True, reminder_time="19:00"
        )
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Я помогу вести личный табель рабочего времени.\n\n"
            "📋 *Открой табель* кнопкой ниже — удобный интерфейс для записи часов и заметок.\n"
            "⏱ Или используй быстрые команды прямо здесь.\n\n"
            "_Например:_\n"
            "`8.5` — часы за сегодня\n"
            "`8.5 #backend Работал над API` — с проектом\n"
            "`7 2025-04-10 #design Встречи` — дата + проект + заметка",
            parse_mode="Markdown",
            reply_markup=main_keyboard(self.config.mini_app_url),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "📖 *Как пользоваться:*\n\n"
            "• `8` или `8.5` — записать часы за сегодня\n"
            "• `8.5 #backend API-ревью` — часы + проект + заметка\n"
            "• `7 2025-04-10` — записать за конкретную дату\n"
            "• `7.5 2025-04-10 #design Прототип` — всё вместе\n\n"
            "📋 *Открыть табель* — полный интерфейс с календарём\n"
            "📊 *Статистика* — итоги за месяц + по проектам\n"
            "📆 *Неделя* — итоги за текущую/прошлую неделю\n"
            "✏️ *Редактировать* — изменить существующую запись\n"
            "🗑 *Удалить* — удалить запись\n"
            "📤 *Экспорт* — скачать CSV за месяц\n"
            "🏷 *По проектам* — аналитика по категориям\n"
            "⏰ *Напоминания* — настроить напоминание\n\n"
            "_Администраторы:_\n"
            "/team\\_stats — сводка по команде\n"
            "/team\\_export — CSV по всем сотрудникам",
            parse_mode="Markdown",
        )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        now = datetime.now()
        stats_data = self.storage.get_month_stats(user_id, now.year, now.month)

        if not stats_data["entries"]:
            await update.message.reply_text("📊 В этом месяце записей пока нет.")
            return

        lines = format_stats_header(
            f"📊 *Статистика за {month_name[now.month]} {now.year}*",
            stats_data["days_worked"],
            stats_data["total_hours"],
            stats_data["avg_hours"],
        )

        project_stats = self.storage.get_project_stats(user_id, now.year, now.month)
        if project_stats:
            lines.append("*По проектам:*")
            for ps in project_stats:
                lines.append(f"  🏷 #{ps['project']}: {ps['total_hours']:.1f}ч ({ps['days']} дн.)")
            lines.append("")

        lines.append("*Последние записи:*")
        for entry in stats_data["entries"][-5:]:
            lines.append(format_entry_line(entry))

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "📆 Выбери неделю:", reply_markup=week_keyboard()
        )

    async def projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        proj_list = self.storage.get_projects(user_id)
        if not proj_list:
            await update.message.reply_text(
                "🏷 Проектов пока нет.\n\nИспользуй `#название` при записи часов:\n"
                "`8 #backend API-ревью`",
                parse_mode="Markdown",
            )
            return
        await update.message.reply_text(
            "🏷 Выбери проект для аналитики:",
            reply_markup=project_keyboard(proj_list),
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if _rate_limiter.is_limited(user_id):
            await update.message.reply_text("⏳ Слишком много запросов. Подожди немного.")
            return

        text = update.message.text.strip()

        if context.user_data.get("edit_mode"):
            return await self._handle_edit_input(update, context)

        if text == "📊 Статистика":
            return await self.stats(update, context)
        if text == "❓ Помощь":
            return await self.help_cmd(update, context)
        if text == "⏱ Записать сегодня":
            await update.message.reply_text(
                "Отправь количество часов (можно с проектом и заметкой):\n"
                "Например: `8` или `7.5 #backend Работал над API`",
                parse_mode="Markdown",
            )
            return
        if text == "📆 Неделя":
            return await self.week(update, context)
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
        if text == "🏷 По проектам":
            return await self.projects(update, context)
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

        date_str = date_type.today().isoformat()
        note = ""
        project = ""

        if len(parts) >= 2:
            try:
                datetime.strptime(parts[1], "%Y-%m-%d")
                date_str = parts[1]
                if len(parts) == 3:
                    project, note = parse_project(parts[2])
            except ValueError:
                project, note = parse_project(" ".join(parts[1:]))

        self.storage.save_entry(user_id, date_str, hours, note, project)

        proj_text = f"\n🏷 Проект: _#{project}_" if project else ""
        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Записано!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Часов: *{hours}*{proj_text}{note_text}",
            parse_mode="Markdown",
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = update.effective_user.id

        if _rate_limiter.is_limited(user_id):
            await query.answer("Слишком много запросов", show_alert=True)
            return

        if data == "cancel":
            await query.edit_message_text("❌ Отменено.")
            return

        if data.startswith("edit:"):
            date_str = data.split(":", 1)[1]
            context.user_data["edit_mode"] = date_str
            await query.edit_message_text(
                f"✏️ Редактирование записи за *{date_str}*.\n\n"
                "Отправь новые часы (можно с проектом и заметкой):\n"
                "Например: `7.5 #backend Обновлённая заметка`",
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

        if data.startswith("week:"):
            period = data.split(":", 1)[1]
            return await self._handle_week(query, user_id, period)

        if data.startswith("project:"):
            proj = data.split(":", 1)[1]
            return await self._handle_project_stats(query, user_id, proj)

    async def handle_web_app_data(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
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
                project = payload.get("project", "")
                self.storage.save_entry(user_id, date_str, hours, note, project)
                proj = f" #{project}" if project else ""
                await update.message.reply_text(
                    f"✅ Сохранено из табеля!\n📅 {date_str} — {hours}ч{proj}",
                )
            elif action == "get_data":
                entries = self.storage.get_entries(user_id)
                await update.message.reply_text(
                    f"📊 Данные синхронизированы ({len(entries)} записей)",
                )
        except Exception as e:
            logger.error(f"Web app data error: {e}")

    async def handle_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.inline_query
        user_id = query.from_user.id
        query_text = query.query.strip()

        from telegram import InlineQueryResultArticle, InputTextMessageContent

        if not query_text:
            entries = self.storage.get_entries(user_id, limit=5)
            results = []
            for entry in entries:
                proj = f" #{entry['project']}" if entry.get("project") else ""
                note = f" — {entry['note']}" if entry.get("note") else ""
                results.append(
                    InlineQueryResultArticle(
                        id=f"entry:{entry['date']}",
                        title=f"{entry['date']}: {entry['hours']}ч{proj}",
                        description=entry.get("note", "Без заметки"),
                        input_message_content=InputTextMessageContent(
                            f"📋 {entry['date']}: {entry['hours']}ч{proj}{note}"
                        ),
                    )
                )
            await query.answer(results, cache_time=10)
            return

        try:
            hours = float(query_text.replace(",", ".").split()[0])
        except (ValueError, IndexError):
            await query.answer([], cache_time=5)
            return

        if hours <= 0 or hours > 24:
            await query.answer([], cache_time=5)
            return

        date_str = date_type.today().isoformat()
        rest = query_text.split(maxsplit=1)
        project, note = "", ""
        if len(rest) > 1:
            project, note = parse_project(rest[1])

        proj_display = f" #{project}" if project else ""
        note_display = f" — {note}" if note else ""
        result = InlineQueryResultArticle(
            id="quick_entry",
            title=f"Записать {hours}ч{proj_display}",
            description=f"{date_str}{note_display}",
            input_message_content=InputTextMessageContent(
                f"✅ Записано {hours}ч{proj_display} за {date_str}"
            ),
        )
        await query.answer([result], cache_time=5)

    async def handle_chosen_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        result = update.chosen_inline_result
        user_id = result.from_user.id
        query_text = result.query.strip()

        try:
            hours = float(query_text.replace(",", ".").split()[0])
        except (ValueError, IndexError):
            return

        if hours <= 0 or hours > 24:
            return

        date_str = date_type.today().isoformat()
        rest = query_text.split(maxsplit=1)
        project, note = "", ""
        if len(rest) > 1:
            project, note = parse_project(rest[1])

        self.storage.save_entry(user_id, date_str, hours, note, project)

    async def team_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not self.storage.is_admin(user_id):
            await update.message.reply_text("❌ Эта команда только для администраторов.")
            return

        now = datetime.now()
        team = self.storage.get_team_month_stats(now.year, now.month)
        if not team:
            await update.message.reply_text("📊 За этот месяц записей от команды нет.")
            return

        lines = [f"👥 *Сводка по команде — {month_name[now.month]} {now.year}*\n"]
        for member in team:
            uid = member["user_id"]
            lines.append(
                f"• Пользователь {uid}: {member['total_hours']:.1f}ч "
                f"({member['days_worked']} дн., среднее {member['avg_hours']:.1f}ч/дн.)"
            )

        total = sum(m["total_hours"] for m in team)
        lines.append(f"\n⏱ *Итого по команде:* {total:.1f}ч")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def team_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not self.storage.is_admin(user_id):
            await update.message.reply_text("❌ Эта команда только для администраторов.")
            return

        now = datetime.now()
        year, month = now.year, now.month
        month_prefix = f"{year}-{month:02d}"
        date_from = f"{month_prefix}-01"
        _, last_day = _monthrange(year, month)
        date_to = f"{month_prefix}-{last_day:02d}"

        entries = self.storage.get_team_entries(date_from, date_to)
        if not entries:
            await update.message.reply_text("📊 За этот месяц записей нет.")
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Пользователь", "Дата", "Часы", "Проект", "Заметка", "Обновлено"])
        for entry in entries:
            writer.writerow([
                entry["user_id"], entry["date"], entry["hours"],
                entry.get("project", ""), entry.get("note", ""), entry.get("updated_at", "")
            ])

        csv_bytes = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        csv_bytes.name = f"team_timesheet_{month_prefix}.csv"
        await update.message.reply_document(csv_bytes)

    async def _show_entries_for_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        entries = self.storage.get_entries(update.effective_user.id, limit=10)
        if not entries:
            await update.message.reply_text("✏️ Записей для редактирования нет.")
            return
        kb = entries_keyboard(entries, "edit")
        await update.message.reply_text(
            "✏️ Выбери запись для редактирования:", reply_markup=kb
        )

    async def _show_entries_for_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        entries = self.storage.get_entries(update.effective_user.id, limit=10)
        if not entries:
            await update.message.reply_text("🗑 Записей для удаления нет.")
            return
        kb = entries_keyboard(entries, "delete")
        await update.message.reply_text(
            "🗑 Выбери запись для удаления:", reply_markup=kb
        )

    async def _handle_edit_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        project, note = "", ""
        if len(parts) > 1:
            project, note = parse_project(parts[1])
        self.storage.save_entry(user_id, date_str, hours, note, project)

        proj_text = f"\n🏷 Проект: _#{project}_" if project else ""
        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Запись обновлена!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Часов: *{hours}*{proj_text}{note_text}",
            parse_mode="Markdown",
        )

    async def _handle_export(self, query, user_id: int, period: str) -> None:
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
        writer.writerow(["Дата", "Часы", "Проект", "Заметка", "Обновлено"])
        for entry in stats_data["entries"]:
            writer.writerow([
                entry["date"], entry["hours"], entry.get("project", ""),
                entry.get("note", ""), entry.get("updated_at", "")
            ])

        csv_bytes = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        csv_bytes.name = f"timesheet_{year}-{month:02d}.csv"

        await query.edit_message_text(f"📤 Экспорт за {month_name[month]} {year}:")
        await query.message.reply_document(csv_bytes)

    async def _handle_week(self, query, user_id: int, period: str) -> None:
        today = date_type.today()
        if period == "current":
            start, end = _week_range(today)
        elif period == "prev":
            start, end = _week_range(today - timedelta(weeks=1))
        else:
            await query.edit_message_text("❌ Неизвестный период.")
            return

        week_data = self.storage.get_week_stats(user_id, start.isoformat(), end.isoformat())
        prev_start, prev_end = _week_range(start - timedelta(weeks=1))
        prev_data = self.storage.get_week_stats(user_id, prev_start.isoformat(), prev_end.isoformat())

        if not week_data["entries"]:
            await query.edit_message_text(
                f"📆 За неделю {start} — {end} записей нет."
            )
            return

        lines = format_stats_header(
            f"📆 *Неделя {start} — {end}*",
            week_data["days_worked"],
            week_data["total_hours"],
            week_data["avg_hours"],
        )

        if prev_data["entries"]:
            diff = week_data["total_hours"] - prev_data["total_hours"]
            sign = "+" if diff >= 0 else ""
            lines.append(f"📊 vs прошлая неделя: {sign}{diff:.1f}ч")

        lines.append("\n*Записи:*")
        for entry in week_data["entries"]:
            lines.append(format_entry_line(entry))

        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    async def _handle_project_stats(self, query, user_id: int, proj: str) -> None:
        now = datetime.now()
        stats_data = self.storage.get_month_stats(user_id, now.year, now.month, project=proj)
        if not stats_data["entries"]:
            await query.edit_message_text(f"🏷 По проекту #{proj} записей нет.")
            return

        lines = format_stats_header(
            f"🏷 *Проект #{proj}* — {month_name[now.month]} {now.year}",
            stats_data["days_worked"],
            stats_data["total_hours"],
            stats_data["avg_hours"],
        )
        lines.append("*Записи:*")
        for entry in stats_data["entries"][-10:]:
            note = f" — {entry['note']}" if entry.get("note") else ""
            lines.append(f"• {entry['date']}: {entry['hours']}ч{note}")

        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    async def _show_reminder_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    async def _handle_reminder_callback(self, query, user_id: int, action: str) -> None:
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
