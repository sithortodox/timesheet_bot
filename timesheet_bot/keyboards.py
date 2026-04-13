from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


def main_keyboard(mini_app_url: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📋 Открыть табель", web_app=WebAppInfo(url=mini_app_url))],
        [
            KeyboardButton("⏱ Записать сегодня"),
            KeyboardButton("📊 Статистика"),
        ],
        [
            KeyboardButton("✏️ Редактировать"),
            KeyboardButton("🗑 Удалить"),
        ],
        [
            KeyboardButton("📤 Экспорт"),
            KeyboardButton("⏰ Напоминания"),
        ],
        [KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def entries_keyboard(entries: list[dict], action: str) -> InlineKeyboardMarkup:
    buttons = []
    for entry in entries[:10]:
        date_str = entry["date"]
        note_preview = f" — {entry['note'][:20]}" if entry.get("note") else ""
        label = f"{date_str}: {entry['hours']}ч{note_preview}"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"{action}:{date_str}")]
        )
    buttons.append(
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    )
    return InlineKeyboardMarkup(buttons)


def confirm_delete_keyboard(date_str: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Да, удалить", callback_data=f"delete_confirm:{date_str}"
                ),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
            ]
        ]
    )


def reminder_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(toggle_label, callback_data="reminder:toggle"),
                InlineKeyboardButton(
                    "🕐 Изменить время", callback_data="reminder:time"
                ),
            ],
            [InlineKeyboardButton("❌ Закрыть", callback_data="cancel")],
        ]
    )


def export_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Текущий месяц", callback_data="export:current"
                ),
                InlineKeyboardButton(
                    "📊 Прошлый месяц", callback_data="export:prev"
                ),
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
    )
