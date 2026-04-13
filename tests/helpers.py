import sys
import os
from unittest.mock import AsyncMock, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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


def make_inline_query(query_text, user_id=123):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id

    iq = MagicMock()
    iq.query = query_text
    iq.from_user = user
    iq.answer = AsyncMock()
    type(update).inline_query = PropertyMock(return_value=iq)

    return update


def make_chosen_result(query_text, user_id=123):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id

    result = MagicMock()
    result.query = query_text
    result.from_user = user
    type(update).chosen_inline_result = PropertyMock(return_value=result)

    return update


def make_context():
    context = MagicMock()
    context.user_data = {}
    context.bot_data = {}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    return context
