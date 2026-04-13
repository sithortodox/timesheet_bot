import os
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from timesheet_bot.config import Config
from timesheet_bot.storage import SqliteStorage


@pytest.fixture
def config(tmp_path):
    return Config(
        bot_token="test_token_123",
        mini_app_url="https://example.com/miniapp",
        db_path=str(tmp_path / "test.db"),
        reminder_check_interval=60,
    )


@pytest.fixture
def storage(config):
    return SqliteStorage(config.db_path)


@pytest.fixture
def handlers(storage, config):
    from timesheet_bot.handlers import Handlers
    return Handlers(storage, config)


def make_update(text=None, user_id=123, first_name="Тест", chat_id=123, web_app_data=None):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.first_name = first_name
    type(update).effective_user = PropertyMock(return_value=user)

    chat = MagicMock()
    chat.id = chat_id
    type(update).effective_chat = PropertyMock(return_value=chat)

    message = MagicMock()
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()
    type(update).message = PropertyMock(return_value=message)

    if web_app_data is not None:
        wad = MagicMock()
        wad.data = web_app_data
        type(message).web_app_data = PropertyMock(return_value=wad)

    if text is not None:
        type(message).text = PropertyMock(return_value=text)

    return update


def make_callback_query(data, user_id=123, chat_id=123):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    type(update).effective_user = PropertyMock(return_value=user)

    query = MagicMock()
    query.answer = AsyncMock()
    query.data = data
    query.edit_message_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    query.message = MagicMock()
    query.message.chat = MagicMock()
    query.message.chat.id = chat_id
    query.message.reply_document = AsyncMock()
    type(update).callback_query = PropertyMock(return_value=query)

    return update


def make_context():
    context = MagicMock()
    context.user_data = {}
    context.bot_data = {}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_token_123")
