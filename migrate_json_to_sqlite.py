"""
Миграция данных из JSON-формата (старый bot.py) в SQLite.

Использование:
    python migrate_json_to_sqlite.py [путь_к_json] [путь_к_db]

По умолчанию: timesheet_data.json → timesheet.db
"""

import json
import sqlite3
import sys
from datetime import datetime


def migrate(json_path: str = "timesheet_data.json", db_path: str = "timesheet.db"):
    if not __import__("os").path.exists(json_path):
        print(f"❌ Файл {json_path} не найден.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entries (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            hours REAL NOT NULL,
            note TEXT DEFAULT '',
            project TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_entries_user_date
            ON entries(user_id, date);

        CREATE TABLE IF NOT EXISTS reminders (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            enabled INTEGER DEFAULT 1,
            reminder_time TEXT DEFAULT '19:00'
        );

        CREATE TABLE IF NOT EXISTS reminder_log (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (user_id, date)
        );

        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL
        );
    """
    )

    total_users = 0
    total_entries = 0

    for user_id_str, user_data in data.items():
        user_id = int(user_id_str)
        entries = user_data.get("entries", {})
        for date_str, entry in entries.items():
            hours = entry.get("hours", 0)
            note = entry.get("note", "")
            updated_at = entry.get("updated_at", datetime.now().isoformat())
            conn.execute(
                """
                INSERT OR REPLACE INTO entries (user_id, date, hours, note, project, updated_at)
                VALUES (?, ?, ?, ?, '', ?)
                """,
                (user_id, date_str, hours, note, updated_at),
            )
            total_entries += 1
        total_users += 1

    conn.commit()
    conn.close()

    print(f"✅ Миграция завершена:")
    print(f"   Пользователей: {total_users}")
    print(f"   Записей: {total_entries}")
    print(f"   {json_path} → {db_path}")


if __name__ == "__main__":
    jpath = sys.argv[1] if len(sys.argv) > 1 else "timesheet_data.json"
    dpath = sys.argv[2] if len(sys.argv) > 2 else "timesheet.db"
    migrate(jpath, dpath)
