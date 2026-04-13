import json
import os
import sys
from datetime import date, datetime
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from helpers import make_update, make_callback_query, make_context, make_inline_query, make_chosen_result


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_start_greeting(self, handlers, storage):
        update = make_update(text="/start", user_id=123, first_name="Иван")
        context = make_context()
        await handlers.start(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Иван" in text
        assert "#backend" in text

    @pytest.mark.asyncio
    async def test_start_creates_reminder(self, handlers, storage):
        update = make_update(text="/start", user_id=123, chat_id=456)
        context = make_context()
        await handlers.start(update, context)
        assert storage.get_reminder(123)["chat_id"] == 456


class TestHelpHandler:
    @pytest.mark.asyncio
    async def test_help_text(self, handlers):
        update = make_update(text="/help", user_id=123)
        context = make_context()
        await handlers.help_cmd(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Как пользоваться" in text
        assert "#backend" in text
        assert "Неделя" in text
        assert "team" in text


class TestStatsHandler:
    @pytest.mark.asyncio
    async def test_stats_empty(self, handlers):
        update = make_update(text="📊 Статистика", user_id=123)
        context = make_context()
        await handlers.stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "пока нет" in text

    @pytest.mark.asyncio
    async def test_stats_with_projects(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "", "backend")
        storage.save_entry(123, "2025-04-02", 7.5, "", "design")
        storage.save_entry(123, "2025-04-03", 8.0, "")
        update = make_update(text="📊 Статистика", user_id=123)
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 5, 12, 0, 0)
            mock_dt.month = 4
            mock_dt.year = 2025
            await handlers.stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "23.5" in text
        assert "#backend" in text
        assert "#design" in text


class TestHandleMessageQuickEntry:
    @pytest.mark.asyncio
    async def test_hours_only(self, handlers, storage):
        update = make_update(text="8", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Записано" in text
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert entries[0]["hours"] == 8.0

    @pytest.mark.asyncio
    async def test_hours_with_project(self, handlers, storage):
        update = make_update(text="8.5 #backend API ревью", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "#backend" in text
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert entries[0]["project"] == "backend"
        assert entries[0]["note"] == "API ревью"

    @pytest.mark.asyncio
    async def test_hours_with_project_only(self, handlers, storage):
        update = make_update(text="8 #design", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert entries[0]["project"] == "design"
        assert entries[0]["note"] == ""

    @pytest.mark.asyncio
    async def test_hours_with_date_and_project(self, handlers, storage):
        update = make_update(text="7 2025-04-10 #backend Спринт", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        entries = storage.get_entries(123, date_from="2025-04-10", date_to="2025-04-10")
        assert entries[0]["project"] == "backend"
        assert entries[0]["note"] == "Спринт"

    @pytest.mark.asyncio
    async def test_hours_with_note(self, handlers, storage):
        update = make_update(text="8.5 Работал над проектом X", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert entries[0]["note"] == "Работал над проектом X"
        assert entries[0]["project"] == ""

    @pytest.mark.asyncio
    async def test_invalid_text_ignored(self, handlers):
        update = make_update(text="привет мир", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_hours_rejected(self, handlers):
        update = make_update(text="0", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        assert "❌" in update.message.reply_text.call_args[0][0]


class TestHandleMessageMenuButtons:
    @pytest.mark.asyncio
    async def test_menu_week(self, handlers):
        update = make_update(text="📆 Неделя", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[1].get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_menu_projects(self, handlers):
        update = make_update(text="🏷 По проектам", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_edit(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_update(text="✏️ Редактировать", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        assert update.message.reply_text.call_args[1].get("reply_markup") is not None


class TestCallbackHandler:
    @pytest.mark.asyncio
    async def test_cancel(self, handlers):
        update = make_callback_query("cancel")
        context = make_context()
        await handlers.handle_callback(update, context)
        assert "Отменено" in update.callback_query.edit_message_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_edit_callback(self, handlers):
        update = make_callback_query("edit:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        assert context.user_data.get("edit_mode") == "2025-04-10"

    @pytest.mark.asyncio
    async def test_delete_confirm(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_callback_query("delete_confirm:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        assert "удалена" in update.callback_query.edit_message_text.call_args[0][0]
        assert storage.get_entries(123) == []

    @pytest.mark.asyncio
    async def test_week_current(self, handlers, storage):
        storage.save_entry(123, "2025-04-07", 8.0)
        storage.save_entry(123, "2025-04-08", 7.5)
        update = make_callback_query("week:current")
        context = make_context()
        with patch("timesheet_bot.handlers.date_type") as mock_date:
            mock_date.today.return_value = date(2025, 4, 8)
            await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "15.5" in text

    @pytest.mark.asyncio
    async def test_week_prev_comparison(self, handlers, storage):
        storage.save_entry(123, "2025-03-31", 8.0)
        storage.save_entry(123, "2025-04-07", 7.5)
        storage.save_entry(123, "2025-04-08", 6.0)
        update = make_callback_query("week:current")
        context = make_context()
        with patch("timesheet_bot.handlers.date_type") as mock_date:
            mock_date.today.return_value = date(2025, 4, 8)
            await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "vs прошлая" in text

    @pytest.mark.asyncio
    async def test_project_stats(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "API", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "UI", "backend")
        update = make_callback_query("project:backend")
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 5, 12, 0, 0)
            mock_dt.month = 4
            mock_dt.year = 2025
            await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "#backend" in text
        assert "15.0" in text

    @pytest.mark.asyncio
    async def test_reminder_toggle(self, handlers, storage):
        storage.set_reminder(123, 123, True, "19:00")
        update = make_callback_query("reminder:toggle")
        context = make_context()
        await handlers.handle_callback(update, context)
        assert storage.get_reminder(123)["enabled"] == 0


class TestEditFlow:
    @pytest.mark.asyncio
    async def test_edit_with_project(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Старая")
        context = make_context()
        context.user_data["edit_mode"] = "2025-04-10"
        update = make_update(text="6 #backend Новая", user_id=123)
        await handlers.handle_message(update, context)
        entries = storage.get_entries(123, date_from="2025-04-10", date_to="2025-04-10")
        assert entries[0]["project"] == "backend"
        assert entries[0]["note"] == "Новая"


class TestWebAppData:
    @pytest.mark.asyncio
    async def test_save_with_project(self, handlers, storage):
        payload = json.dumps({"action": "save_entry", "date": "2025-04-10", "hours": 8, "note": "API", "project": "backend"})
        update = make_update(user_id=123, web_app_data=payload)
        context = make_context()
        await handlers.handle_web_app_data(update, context)
        entries = storage.get_entries(123)
        assert entries[0]["project"] == "backend"

    @pytest.mark.asyncio
    async def test_invalid_json(self, handlers):
        update = make_update(user_id=123, web_app_data="not json")
        context = make_context()
        await handlers.handle_web_app_data(update, context)
        update.message.reply_text.assert_not_called()


class TestTeamStats:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, handlers, storage):
        update = make_update(text="/team_stats", user_id=123)
        context = make_context()
        await handlers.team_stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "администратор" in text

    @pytest.mark.asyncio
    async def test_admin_sees_team(self, handlers, storage):
        storage.set_admin(123, 123)
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(456, "2025-04-01", 7.0)
        update = make_update(text="/team_stats", user_id=123)
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 5, 12, 0, 0)
            mock_dt.month = 4
            mock_dt.year = 2025
            await handlers.team_stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Сводка" in text
        assert "команде" in text

    @pytest.mark.asyncio
    async def test_team_export_non_admin(self, handlers, storage):
        update = make_update(text="/team_export", user_id=123)
        context = make_context()
        await handlers.team_export(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "администратор" in text

    @pytest.mark.asyncio
    async def test_team_export_admin(self, handlers, storage):
        storage.set_admin(123, 123)
        storage.set_reminder(123, 123, True)
        storage.save_entry(123, "2025-04-01", 8.0)
        update = make_update(text="/team_export", user_id=123)
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 10, 12, 0, 0)
            mock_dt.month = 4
            mock_dt.year = 2025
            await handlers.team_export(update, context)
        update.message.reply_document.assert_called_once()


class TestInlineQuery:
    @pytest.mark.asyncio
    async def test_inline_empty_shows_entries(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Работал")
        update = make_inline_query("", user_id=123)
        context = make_context()
        await handlers.handle_inline(update, context)
        update.inline_query.answer.assert_called_once()
        results = update.inline_query.answer.call_args[0][0]
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_inline_with_hours(self, handlers, storage):
        update = make_inline_query("8 #backend", user_id=123)
        context = make_context()
        await handlers.handle_inline(update, context)
        update.inline_query.answer.assert_called_once()
        results = update.inline_query.answer.call_args[0][0]
        assert len(results) == 1
        assert "8.0ч" in results[0].title

    @pytest.mark.asyncio
    async def test_inline_invalid_text(self, handlers):
        update = make_inline_query("абв", user_id=123)
        context = make_context()
        await handlers.handle_inline(update, context)
        results = update.inline_query.answer.call_args[0][0]
        assert len(results) == 0


class TestChosenInlineResult:
    @pytest.mark.asyncio
    async def test_chosen_saves_entry(self, handlers, storage):
        update = make_chosen_result("8 #backend API", user_id=123)
        context = make_context()
        await handlers.handle_chosen_inline(update, context)
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert len(entries) == 1
        assert entries[0]["hours"] == 8.0
        assert entries[0]["project"] == "backend"

    @pytest.mark.asyncio
    async def test_chosen_invalid_ignored(self, handlers, storage):
        update = make_chosen_result("абв", user_id=123)
        context = make_context()
        await handlers.handle_chosen_inline(update, context)
        assert storage.get_entries(123) == []
