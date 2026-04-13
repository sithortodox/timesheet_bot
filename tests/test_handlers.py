import json
import os
import sys
from datetime import date, datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers import make_update, make_callback_query, make_context


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_start_greeting(self, handlers, storage):
        update = make_update(text="/start", user_id=123, first_name="Иван")
        context = make_context()
        await handlers.start(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Иван" in text
        assert "Привет" in text

    @pytest.mark.asyncio
    async def test_start_creates_reminder(self, handlers, storage):
        update = make_update(text="/start", user_id=123, chat_id=456)
        context = make_context()
        await handlers.start(update, context)
        reminder = storage.get_reminder(123)
        assert reminder is not None
        assert reminder["chat_id"] == 456
        assert reminder["enabled"] == 1


class TestHelpHandler:
    @pytest.mark.asyncio
    async def test_help_text(self, handlers):
        update = make_update(text="/help", user_id=123)
        context = make_context()
        await handlers.help_cmd(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Как пользоваться" in text
        assert "Редактировать" in text
        assert "Экспорт" in text


class TestStatsHandler:
    @pytest.mark.asyncio
    async def test_stats_empty(self, handlers):
        update = make_update(text="📊 Статистика", user_id=123)
        context = make_context()
        await handlers.stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "пока нет" in text

    @pytest.mark.asyncio
    async def test_stats_with_data(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "X")
        storage.save_entry(123, "2025-04-02", 7.5, "Y")
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
        assert "3" in text


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
        assert len(entries) == 1
        assert entries[0]["hours"] == 8.0

    @pytest.mark.asyncio
    async def test_hours_with_comma(self, handlers, storage):
        update = make_update(text="7,5", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "7.5" in text

    @pytest.mark.asyncio
    async def test_hours_with_note(self, handlers, storage):
        update = make_update(text="8.5 Работал над проектом X", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "8.5" in text
        today = date.today().isoformat()
        entries = storage.get_entries(123, date_from=today, date_to=today)
        assert entries[0]["note"] == "Работал над проектом X"

    @pytest.mark.asyncio
    async def test_hours_with_date(self, handlers, storage):
        update = make_update(text="7 2025-04-10", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "2025-04-10" in text
        entries = storage.get_entries(123, date_from="2025-04-10", date_to="2025-04-10")
        assert entries[0]["hours"] == 7.0

    @pytest.mark.asyncio
    async def test_hours_with_date_and_note(self, handlers, storage):
        update = make_update(text="7.5 2025-04-10 Встречи и документация", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        entries = storage.get_entries(123, date_from="2025-04-10", date_to="2025-04-10")
        assert entries[0]["hours"] == 7.5
        assert entries[0]["note"] == "Встречи и документация"

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
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text

    @pytest.mark.asyncio
    async def test_over_24_hours_rejected(self, handlers):
        update = make_update(text="25", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text


class TestHandleMessageMenuButtons:
    @pytest.mark.asyncio
    async def test_menu_stats(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        update = make_update(text="📊 Статистика", user_id=123)
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 5, 12, 0, 0)
            mock_dt.month = 4
            mock_dt.year = 2025
            await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_help(self, handlers):
        update = make_update(text="❓ Помощь", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Как пользоваться" in text

    @pytest.mark.asyncio
    async def test_menu_record_today(self, handlers):
        update = make_update(text="⏱ Записать сегодня", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_edit(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_update(text="✏️ Редактировать", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[1].get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_menu_edit_empty(self, handlers):
        update = make_update(text="✏️ Редактировать", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "нет" in text

    @pytest.mark.asyncio
    async def test_menu_delete(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_update(text="🗑 Удалить", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_menu_export(self, handlers):
        update = make_update(text="📤 Экспорт", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[1].get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_menu_reminders(self, handlers):
        update = make_update(text="⏰ Напоминания", user_id=123)
        context = make_context()
        await handlers.handle_message(update, context)
        update.message.reply_text.assert_called_once()


class TestCallbackHandler:
    @pytest.mark.asyncio
    async def test_cancel(self, handlers):
        update = make_callback_query("cancel")
        context = make_context()
        await handlers.handle_callback(update, context)
        update.callback_query.edit_message_text.assert_called_once()
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "Отменено" in text

    @pytest.mark.asyncio
    async def test_edit_callback(self, handlers):
        update = make_callback_query("edit:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        assert context.user_data.get("edit_mode") == "2025-04-10"
        update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_callback(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_callback_query("delete:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        update.callback_query.edit_message_reply_markup.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_confirm(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        update = make_callback_query("delete_confirm:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "удалена" in text
        entries = storage.get_entries(123)
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_delete_confirm_nonexistent(self, handlers):
        update = make_callback_query("delete_confirm:2025-04-10")
        context = make_context()
        await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "не найдена" in text

    @pytest.mark.asyncio
    async def test_export_current(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "Работал")
        update = make_callback_query("export:current")
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 10, 12, 0, 0)
            mock_dt.year = 2025
            mock_dt.month = 4
            await handlers.handle_callback(update, context)
        update.callback_query.edit_message_text.assert_called_once()
        update.callback_query.message.reply_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_empty(self, handlers):
        update = make_callback_query("export:current")
        context = make_context()
        with patch("timesheet_bot.handlers.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 10, 12, 0, 0)
            mock_dt.year = 2025
            mock_dt.month = 4
            await handlers.handle_callback(update, context)
        text = update.callback_query.edit_message_text.call_args[0][0]
        assert "нет" in text

    @pytest.mark.asyncio
    async def test_reminder_toggle(self, handlers, storage):
        storage.set_reminder(123, 123, True, "19:00")
        update = make_callback_query("reminder:toggle")
        context = make_context()
        await handlers.handle_callback(update, context)
        r = storage.get_reminder(123)
        assert r["enabled"] == 0


class TestEditFlow:
    @pytest.mark.asyncio
    async def test_edit_input(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Старая")
        context = make_context()
        context.user_data["edit_mode"] = "2025-04-10"
        update = make_update(text="6 Новая заметка", user_id=123)
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "обновлена" in text
        assert "edit_mode" not in context.user_data
        entries = storage.get_entries(123, date_from="2025-04-10", date_to="2025-04-10")
        assert entries[0]["hours"] == 6.0
        assert entries[0]["note"] == "Новая заметка"

    @pytest.mark.asyncio
    async def test_edit_invalid_input(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Старая")
        context = make_context()
        context.user_data["edit_mode"] = "2025-04-10"
        update = make_update(text="абв", user_id=123)
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text
        assert context.user_data.get("edit_mode") == "2025-04-10"

    @pytest.mark.asyncio
    async def test_edit_over_24(self, handlers, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        context = make_context()
        context.user_data["edit_mode"] = "2025-04-10"
        update = make_update(text="25", user_id=123)
        await handlers.handle_message(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text


class TestWebAppData:
    @pytest.mark.asyncio
    async def test_save_entry_action(self, handlers, storage):
        payload = json.dumps({"action": "save_entry", "date": "2025-04-10", "hours": 8, "note": "Из апп"})
        update = make_update(user_id=123, web_app_data=payload)
        context = make_context()
        await handlers.handle_web_app_data(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "2025-04-10" in text
        entries = storage.get_entries(123)
        assert entries[0]["hours"] == 8.0

    @pytest.mark.asyncio
    async def test_get_data_action(self, handlers, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-02", 7.5)
        payload = json.dumps({"action": "get_data"})
        update = make_update(user_id=123, web_app_data=payload)
        context = make_context()
        await handlers.handle_web_app_data(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "2" in text

    @pytest.mark.asyncio
    async def test_invalid_json(self, handlers):
        update = make_update(user_id=123, web_app_data="not json")
        context = make_context()
        await handlers.handle_web_app_data(update, context)
        update.message.reply_text.assert_not_called()
