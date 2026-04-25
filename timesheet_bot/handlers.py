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
    format_money,
    format_stats_header,
    parse_payment,
    parse_project,
    parse_shift_time,
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
            "`09:00 18:00` — начало и конец смены за сегодня\n"
            "`09:00 18:00 #backend Работал над API` — с проектом\n"
            "`09:00 18:00 $5000 #backend` — с оплатой и проектом\n"            "`09:00 18:00 2025-04-10 #design Встречи` — дата + проект + заметка",
            parse_mode="Markdown",
            reply_markup=main_keyboard(self.config.mini_app_url, user_id=update.effective_user.id),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "📖 *Как пользоваться:*\n\n"
            "• `09:00 18:00` — записать смену за сегодня\n"
            "• `09:00 18:00 $5000` — с оплатой за смену\n"
            "• `09:00 18:00 $5000 #backend API-ревью` — оплата + проект + заметка\n"
            "• `09:00 18:00 2025-04-10` — за конкретную дату\n"
            "• `09:00 18:00 2025-04-10 #design Прототип` — всё вместе\n\n"
            "🎤 *Голосовой ввод:* отправь голосовое — скажи «девять восемнадцать цех1»\n\n"
            "💼 */salary 50000* — записать получение зарплаты\n"
            "💼 */salary 30000 2026-04-15 Аванс* — за дату с заметкой\n"
            "🛌 */dayoff* — отметить сегодня как выходной\n"
            "🛌 */dayoff 2026-04-20* — выходной за конкретную дату\n\n"
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
        month_prefix = f"{now.year:04d}-{now.month:02d}"
        month_salary = self.storage.get_income_total(user_id, date_from=f"{month_prefix}-01")
        total_payment = sum(e.get("payment", 0) or 0 for e in stats_data["entries"])

        if not stats_data["entries"] and month_salary == 0:
            await update.message.reply_text("📊 В этом месяце записей пока нет.")
            return

        lines = format_stats_header(
            f"📊 *Статистика за {month_name[now.month]} {now.year}*",
            stats_data["days_worked"],
            stats_data["total_hours"],
            stats_data["avg_hours"],
        )

        if total_payment > 0 or month_salary > 0:
            lines.append(f"💵 За смены: *{format_money(total_payment)}*")
            if month_salary > 0:
                lines.append(f"💼 Зарплата: *{format_money(month_salary)}*")
            lines.append(f"💰 Итого: *{format_money(total_payment + month_salary)}*\n")

        project_stats = self.storage.get_project_stats(user_id, now.year, now.month)
        if project_stats:
            lines.append("*По проектам:*")
            for ps in project_stats:
                pay = format_money(ps.get("total_payment", 0)) if ps.get("total_payment", 0) > 0 else ""
                lines.append(f"  🏷 #{ps['project']}: {ps['total_hours']:.1f}ч ({ps['days']} дн.) {pay}")
            lines.append("")

        lines.append("*Последние записи:*")
        for entry in stats_data["entries"][-5:]:
            lines.append(format_entry_line(entry))

        if month_salary > 0:
            income_items = self.storage.get_income(user_id, date_from=f"{month_prefix}-01")
            if income_items:
                lines.append("\n*Зарплата:*")
                for item in income_items:
                    note = f" — _{item['note']}_" if item.get("note") else ""
                    lines.append(f"  💼 {item['date']}: {format_money(item['amount'])}{note}")

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
                "🏷 Проектов пока нет.\n\nИспользуй `#название` при записи смены:\n"
                "`09:00 18:00 #backend API-ревью`",
                parse_mode="Markdown",
            )
            return
        await update.message.reply_text(
            "🏷 Выбери проект для аналитики:",
            reply_markup=project_keyboard(proj_list),
        )

    async def salary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "💰 Введи зарплату:\n"
                "`/salary 50000` — за сегодня\n"
                "`/salary 50000 2026-04-15 Аванс` — за дату с заметкой",
                parse_mode="Markdown",
            )
            return

        try:
            amount = float(args[0].replace(",", "."))
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Неверная сумма.")
            return

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0.")
            return

        date_str = date_type.today().isoformat()
        note = ""
        if len(args) >= 2:
            try:
                datetime.strptime(args[1], "%Y-%m-%d")
                date_str = args[1]
                if len(args) > 2:
                    note = " ".join(args[2:])
            except ValueError:
                note = " ".join(args[1:])

        self.storage.save_income(user_id, date_str, amount, note)
        note_text = f"\n📝 _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Зарплата записана!\n"
            f"📅 Дата: *{date_str}*\n"
            f"💵 Сумма: *{format_money(amount)}*{note_text}",
            parse_mode="Markdown",
        )

    async def budget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        now = datetime.now()
        month_prefix = f"{now.year:04d}-{now.month:02d}"

        month_data = self.storage.get_month_budget(user_id, now.year, now.month)
        month_salary = self.storage.get_income_total(user_id, date_from=f"{month_prefix}-01")
        total = self.storage.get_total_budget(user_id)
        total_salary = self.storage.get_income_total(user_id)

        has_any = total["total_days"] > 0 or total_salary > 0
        if not has_any:
            await update.message.reply_text("💰 Записей пока нет.")
            return

        lines = [f"💰 *Бюджет за {month_name[now.month]} {now.year}*\n"]

        month_payment = month_data.get("total_payment", 0)
        month_total_income = month_payment + month_salary

        if month_data["entries"]:
            lines.append(f"⏱ Отработано: *{month_data['total_hours']:.1f} ч*")
            lines.append(f"💵 За смены: *{format_money(month_payment)}*")
        if month_salary > 0:
            lines.append(f"💼 Зарплата: *{format_money(month_salary)}*")
        lines.append(f"💰 Итого за месяц: *{format_money(month_total_income)}*")

        if month_data["entries"]:
            lines.append(f"✅ Оплачено смен: *{month_data['paid_days']}*")
            lines.append(f"⏳ Не оплачено: *{month_data['unpaid_days']}*\n")

            project_income = month_data["project_income"]
            paid_projects = {k: v for k, v in project_income.items() if v > 0}
            if paid_projects:
                lines.append("*Доход по проектам:*")
                for proj, income in sorted(paid_projects.items(), key=lambda x: -x[1]):
                    lines.append(f"  🏷 #{proj}: {format_money(income)}")
                lines.append("")

            avg_d = month_total_income / max(month_data["paid_days"], 1)
            avg_h = month_total_income / max(month_data["total_hours"], 1)
            if month_total_income > 0:
                lines.append(f"📈 Среднее в день: *{format_money(avg_d)}*")
                lines.append(f"📈 Среднее в час: *{format_money(avg_h)}*")

        total_all = total["total_payment"] + total_salary
        lines.append("\n📊 *За всё время*\n")
        lines.append(f"⏱ Часов: *{total['total_hours']:.1f}*")
        lines.append(f"💵 За смены: *{format_money(total['total_payment'])}*")
        if total_salary > 0:
            lines.append(f"💼 Зарплата: *{format_money(total_salary)}*")
        lines.append(f"💰 Всего получено: *{format_money(total_all)}*")
        lines.append(f"📅 Смен: *{total['total_days']}* (оплачено {total['paid_days']}, не оплачено {total['unpaid_days']})")

        total_projects = {k: v for k, v in total["project_income"].items() if v > 0}
        if total_projects:
            lines.append("\n*Доход по проектам:*")
            for proj, income in sorted(total_projects.items(), key=lambda x: -x[1]):
                lines.append(f"  🏷 #{proj}: {format_money(income)}")

        if total["monthly"]:
            lines.append("\n*По месяцам:*")
            for m in total["monthly"][:6]:
                lines.append(f"  📅 {m['month']}: {m['hours']:.0f}ч, {format_money(m['payment'])}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def dayoff(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        args = context.args or []
        date_str = date_type.today().isoformat()
        if args:
            try:
                datetime.strptime(args[0], "%Y-%m-%d")
                date_str = args[0]
            except ValueError:
                await update.message.reply_text("❌ Формат даты: ГГГГ-ММ-ДД\nПример: `/dayoff 2026-04-20`", parse_mode="Markdown")
                return
        self.storage.save_entry(user_id, date_str, 0, "", "", "", "", 0, day_type="dayoff")
        await update.message.reply_text(
            f"🛌 *Выходной отмечен!*\n📅 Дата: *{date_str}*",
            parse_mode="Markdown",
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if _rate_limiter.is_limited(user_id):
            await update.message.reply_text("⏳ Слишком много запросов. Подожди немного.")
            return

        text = (update.message.text or "").strip()

        if context.user_data.get("edit_mode"):
            return await self._handle_edit_input(update, context)

        if text == "📊 Статистика":
            return await self.stats(update, context)
        if text == "❓ Помощь":
            return await self.help_cmd(update, context)
        if text == "⏱ Записать смену":
            await update.message.reply_text(
                "Отправь начало и конец смены (можно с проектом и заметкой):\n"
                "Например: `09:00 18:00` или `09:00 18:00 #backend Работал над API`",
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
        if text == "💰 Бюджет":
            return await self.budget(update, context)
        if text == "🛌 Выходной":
            context.args = []
            return await self.dayoff(update, context)

        parts = text.split(maxsplit=3)
        if len(parts) < 2:
            return

        start_time = parts[0]
        end_time = parts[1]
        hours = parse_shift_time(start_time, end_time)
        if hours is None:
            return

        date_str = date_type.today().isoformat()
        note = ""
        project = ""

        rest_parts = parts[2:] if len(parts) > 2 else []
        payment = 0
        if rest_parts:
            rest = " ".join(rest_parts)
            payment, rest = parse_payment(rest)
            try:
                candidate = rest.split()[0]
                datetime.strptime(candidate, "%Y-%m-%d")
                date_str = candidate
                remaining = rest.split(maxsplit=1)
                if len(remaining) > 1:
                    project, note = parse_project(remaining[1])
            except ValueError:
                project, note = parse_project(rest)

        self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, payment, "work")

        pay_text = f"\n💵 Оплата: _{format_money(payment)}_" if payment > 0 else ""
        proj_text = f"\n🏷 Проект: _#{project}_" if project else ""
        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Записано!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Смена: *{start_time}-{end_time}* → *{hours:.1f}ч*{pay_text}{proj_text}{note_text}",
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
                "Отправь новые начало и конец смены:\n"
                "Например: `09:00 18:00 #backend Обновлённая заметка`",
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

        if data.startswith("yesterday:"):
            parts = data.split(":")
            if len(parts) == 4 and parts[1] == "dayoff":
                date_str = parts[2]
                self.storage.save_entry(user_id, date_str, 0, "", "", "", "", 0, day_type="dayoff")
                await query.edit_message_text(f"🛌 Выходной за *{date_str}* отмечен!", parse_mode="Markdown")
            elif len(parts) == 5:
                start_time = parts[1]
                end_time = parts[2]
                date_str = parts[3]
                hours = parse_shift_time(start_time, end_time)
                if hours:
                    self.storage.save_entry(user_id, date_str, hours, "", "", start_time, end_time, 0, "work")
                    await query.edit_message_text(f"✅ Записано за *{date_str}*: {start_time}-{end_time} → *{hours:.1f}ч*", parse_mode="Markdown")
                else:
                    await query.edit_message_text("❌ Неверное время")
            return

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
                start_time = payload.get("start_time", "")
                end_time = payload.get("end_time", "")
                hours = parse_shift_time(start_time, end_time) if start_time and end_time else float(payload.get("hours", 0))
                note = payload.get("note", "")
                project = payload.get("project", "").lower()
                payment = float(payload.get("payment", 0))
                day_type = payload.get("day_type", "work")
                if day_type not in ("work", "dayoff"):
                    day_type = "work"
                self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, payment, day_type)
                shift = f" ({start_time}-{end_time})" if start_time and end_time else ""
                proj = f" #{project}" if project else ""
                await update.message.reply_text(
                    f"✅ Сохранено из табеля!\n📅 {date_str} — {hours:.1f}ч{shift}{proj}",
                )
            elif action == "save_income":
                date_str = payload["date"]
                amount = float(payload["amount"])
                note = payload.get("note", "")
                self.storage.save_income(user_id, date_str, amount, note)
                await update.message.reply_text(
                    f"✅ Зарплата записана из табеля!\n📅 {date_str} — {format_money(amount)}",
                )
            elif action == "get_data":
                entries = self.storage.get_entries(user_id)
                await update.message.reply_text(
                    f"📊 Данные синхронизированы ({len(entries)} записей)",
                )
        except Exception as e:
            logger.error(f"Web app data error: {e}")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        caption = update.message.caption or ""
        date_str = date_type.today().isoformat()

        try:
            import re
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", caption)
            if date_match:
                date_str = date_match.group(1)

            photo = update.message.photo[-1]
            file = await photo.get_file()

            import os
            photo_dir = os.path.join("/app/data/photos", str(user_id), date_str)
            os.makedirs(photo_dir, exist_ok=True)

            import uuid
            ext = ".jpg"
            file_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(photo_dir, file_name)
            await file.download_to_drive(file_path)

            note = caption.strip()
            self.storage.save_photo(user_id, date_str, file_name, telegram_file_id=file.file_id, caption=note)
            await update.message.reply_text(
                f"📷 Фото сохранено!\n📅 Дата: *{date_str}*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Photo handler error: {e}")
            await update.message.reply_text("❌ Ошибка сохранения фото.")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            voice = update.message.voice
            file = await voice.get_file()

            import os
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
            tmp_path = tmp.name
            tmp.close()
            await file.download_to_drive(tmp_path)

            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(tmp_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")

            os.unlink(tmp_path)

            logger.info(f"Voice from {user_id}: {text}")
            parts = text.split()
            start_time = ""
            end_time = ""
            hours = None
            if len(parts) >= 2:
                hours = parse_shift_time(parts[0], parts[1])
                if hours:
                    start_time = parts[0]
                    end_time = parts[1]

            if hours is None:
                await update.message.reply_text(
                    f"🎤 Распознано: _{text}_\n\n"
                    "Не удалось определить смену. Скажи например: «девять восемнадцать»",
                    parse_mode="Markdown",
                )
                return

            date_str = date_type.today().isoformat()
            project = ""
            note = ""
            if len(parts) > 2:
                rest = " ".join(parts[2:])
                project, note = parse_project(rest)

            self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, 0, "work")
            proj_text = f"\n🏷 Проект: _#{project}_" if project else ""
            note_text = f"\n📝 Заметка: _{note}_" if note else ""
            await update.message.reply_text(
                f"✅ Записано из голосового!\n"
                f"📅 Дата: *{date_str}*\n"
                f"⏱ Смена: *{start_time}-{end_time}* → *{hours:.1f}ч*{proj_text}{note_text}",
                parse_mode="Markdown",
            )
        except sr.UnknownValueError:
            await update.message.reply_text("🎤 Не удалось распознать речь. Попробуй ещё раз.")
        except sr.RequestError as e:
            logger.error(f"Speech API error: {e}")
            await update.message.reply_text("❌ Сервис распознавания недоступен. Попробуй позже.")
        except Exception as e:
            logger.error(f"Voice handler error: {e}")
            await update.message.reply_text("❌ Ошибка обработки голосового сообщения.")

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
                shift = f" {entry.get('start_time', '')}-{entry.get('end_time', '')}" if entry.get("start_time") else ""
                results.append(
                    InlineQueryResultArticle(
                        id=f"entry:{entry['date']}",
                        title=f"{entry['date']}: {entry['hours']}ч{shift}{proj}",
                        description=entry.get("note", "Без заметки"),
                        input_message_content=InputTextMessageContent(
                            f"📋 {entry['date']}: {entry['hours']}ч{shift}{proj}{note}"
                        ),
                    )
                )
            await query.answer(results, cache_time=10)
            return

        parts = query_text.split()
        start_time, end_time = "", ""
        hours = None
        if len(parts) >= 2:
            hours = parse_shift_time(parts[0], parts[1])
            if hours is not None:
                start_time = parts[0]
                end_time = parts[1]

        if hours is None:
            await query.answer([], cache_time=5)
            return

        date_str = date_type.today().isoformat()
        project, note = "", ""
        if len(parts) > 2:
            project, note = parse_project(" ".join(parts[2:]))

        proj_display = f" #{project}" if project else ""
        result = InlineQueryResultArticle(
            id="quick_entry",
            title=f"Записать {start_time}-{end_time} ({hours:.1f}ч){proj_display}",
            description=f"{date_str}",
            input_message_content=InputTextMessageContent(
                f"✅ Записана смена {start_time}-{end_time} ({hours:.1f}ч){proj_display} за {date_str}"
            ),
        )
        await query.answer([result], cache_time=5)

    async def handle_chosen_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        result = update.chosen_inline_result
        user_id = result.from_user.id
        query_text = result.query.strip()

        parts = query_text.split()
        start_time, end_time = "", ""
        hours = None
        if len(parts) >= 2:
            hours = parse_shift_time(parts[0], parts[1])
            if hours is not None:
                start_time = parts[0]
                end_time = parts[1]

        if hours is None:
            return

        date_str = date_type.today().isoformat()
        project, note = "", ""
        if len(parts) > 2:
            project, note = parse_project(" ".join(parts[2:]))

        self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time)

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
        writer.writerow(["Пользователь", "Дата", "Начало", "Конец", "Часы", "Проект", "Заметка", "Обновлено"])
        for entry in entries:
            writer.writerow([
                entry["user_id"], entry["date"],
                entry.get("start_time", ""), entry.get("end_time", ""),
                entry["hours"],
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

        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            context.user_data["edit_mode"] = date_str
            await update.message.reply_text("❌ Укажи начало и конец смены: `09:00 18:00`", parse_mode="Markdown")
            return

        start_time = parts[0]
        end_time = parts[1]
        hours = parse_shift_time(start_time, end_time)
        if hours is None:
            context.user_data["edit_mode"] = date_str
            await update.message.reply_text("❌ Неверный формат времени. Пример: `09:00 18:00`", parse_mode="Markdown")
            return

        project, note = "", ""
        payment = 0
        if len(parts) > 2:
            rest = " ".join(parts[2:])
            payment, rest = parse_payment(rest)
            project, note = parse_project(rest)
        self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, payment, "work")

        pay_text = f"\n💵 Оплата: _{format_money(payment)}_" if payment > 0 else ""
        proj_text = f"\n🏷 Проект: _#{project}_" if project else ""
        note_text = f"\n📝 Заметка: _{note}_" if note else ""
        await update.message.reply_text(
            f"✅ Запись обновлена!\n"
            f"📅 Дата: *{date_str}*\n"
            f"⏱ Смена: *{start_time}-{end_time}* → *{hours:.1f}ч*{pay_text}{proj_text}{note_text}",
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
        writer.writerow(["Дата", "Начало", "Конец", "Часы", "Проект", "Заметка", "Обновлено"])
        for entry in stats_data["entries"]:
            writer.writerow([
                entry["date"],
                entry.get("start_time", ""), entry.get("end_time", ""),
                entry["hours"], entry.get("project", ""),
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
            lines.append(format_entry_line(entry))

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
            f"Бот напомнит записать смену, если ты ещё не внёс запись за день."
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
