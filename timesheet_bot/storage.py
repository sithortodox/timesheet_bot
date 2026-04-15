from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime


class StorageBase(ABC):
    @abstractmethod
    def get_entries(
        self, user_id: int, date_from: str = None, date_to: str = None,
        limit: int = None, project: str = None
    ) -> list[dict]: ...

    @abstractmethod
    def save_entry(
        self, user_id: int, date_str: str, hours: float, note: str = "",
        project: str = "", start_time: str = "", end_time: str = "",
        payment: float = 0
    ) -> dict: ...

    @abstractmethod
    def delete_entry(self, user_id: int, date_str: str) -> bool: ...

    @abstractmethod
    def get_month_stats(
        self, user_id: int, year: int, month: int, project: str = None
    ) -> dict: ...

    @abstractmethod
    def get_week_stats(self, user_id: int, date_from: str, date_to: str) -> dict: ...

    @abstractmethod
    def get_project_stats(
        self, user_id: int, year: int, month: int
    ) -> list[dict]: ...

    @abstractmethod
    def get_projects(self, user_id: int) -> list[str]: ...

    @abstractmethod
    def get_month_budget(
        self, user_id: int, year: int, month: int
    ) -> dict: ...

    @abstractmethod
    def set_reminder(
        self, user_id: int, chat_id: int, enabled: bool, reminder_time: str = "19:00"
    ) -> None: ...

    @abstractmethod
    def get_reminder(self, user_id: int) -> dict | None: ...

    @abstractmethod
    def get_all_reminders(self) -> list[dict]: ...

    @abstractmethod
    def get_users_without_entry(self, date_str: str) -> list[dict]: ...

    @abstractmethod
    def mark_reminder_sent(self, user_id: int, date_str: str) -> None: ...

    @abstractmethod
    def is_reminder_sent(self, user_id: int, date_str: str) -> bool: ...

    @abstractmethod
    def set_admin(self, user_id: int, chat_id: int) -> None: ...

    @abstractmethod
    def is_admin(self, user_id: int) -> bool: ...

    @abstractmethod
    def remove_admin(self, user_id: int) -> bool: ...

    @abstractmethod
    def get_all_admins(self) -> list[dict]: ...

    @abstractmethod
    def get_team_entries(
        self, date_from: str, date_to: str, project: str = None
    ) -> list[dict]: ...

    @abstractmethod
    def get_team_month_stats(self, year: int, month: int) -> list[dict]: ...

    @abstractmethod
    def close(self) -> None: ...


class SqliteStorage(StorageBase):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                hours REAL NOT NULL,
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                note TEXT DEFAULT '',
                project TEXT DEFAULT '',
                payment REAL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, date)
            );
            CREATE INDEX IF NOT EXISTS idx_entries_user_date
                ON entries(user_id, date);
            CREATE INDEX IF NOT EXISTS idx_entries_project
                ON entries(user_id, project);

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
        for col in ("start_time", "end_time"):
            try:
                conn.execute(f"ALTER TABLE entries ADD COLUMN {col} TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE entries ADD COLUMN payment REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_entries(
        self, user_id: int, date_from: str = None, date_to: str = None,
        limit: int = None, project: str = None
    ) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM entries WHERE user_id = ?"
        params: list = [user_id]
        if date_from:
            query += " AND date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND date <= ?"
            params.append(date_to)
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY date DESC"
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def save_entry(
        self, user_id: int, date_str: str, hours: float, note: str = "",
        project: str = "", start_time: str = "", end_time: str = "",
        payment: float = 0
    ) -> dict:
        updated_at = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO entries (user_id, date, hours, start_time, end_time, note, project, payment, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                hours=excluded.hours, start_time=excluded.start_time,
                end_time=excluded.end_time, note=excluded.note,
                project=excluded.project, payment=excluded.payment,
                updated_at=excluded.updated_at
            """,
            (user_id, date_str, hours, start_time, end_time, note, project, payment, updated_at),
        )
        conn.commit()
        return {
            "user_id": user_id,
            "date": date_str,
            "hours": hours,
            "start_time": start_time,
            "end_time": end_time,
            "note": note,
            "project": project,
            "payment": payment,
            "updated_at": updated_at,
        }

    def delete_entry(self, user_id: int, date_str: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM entries WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_month_stats(
        self, user_id: int, year: int, month: int, project: str = None
    ) -> dict:
        month_prefix = f"{year:04d}-{month:02d}"
        conn = self._get_conn()
        query = "SELECT date, hours, start_time, end_time, note, project, payment FROM entries WHERE user_id = ? AND date LIKE ?"
        params: list = [user_id, f"{month_prefix}%"]
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        entries = [dict(r) for r in rows]
        total_hours = sum(e["hours"] for e in entries)
        days_worked = len(entries)
        avg_hours = total_hours / days_worked if days_worked else 0
        return {
            "entries": entries,
            "total_hours": total_hours,
            "days_worked": days_worked,
            "avg_hours": avg_hours,
        }

    def get_week_stats(self, user_id: int, date_from: str, date_to: str) -> dict:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT date, hours, start_time, end_time, note, project, payment FROM entries "
            "WHERE user_id = ? AND date >= ? AND date <= ? ORDER BY date",
            (user_id, date_from, date_to),
        ).fetchall()
        entries = [dict(r) for r in rows]
        total_hours = sum(e["hours"] for e in entries)
        days_worked = len(entries)
        avg_hours = total_hours / days_worked if days_worked else 0
        return {
            "entries": entries,
            "total_hours": total_hours,
            "days_worked": days_worked,
            "avg_hours": avg_hours,
        }

    def get_project_stats(self, user_id: int, year: int, month: int) -> list[dict]:
        month_prefix = f"{year:04d}-{month:02d}"
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT project, SUM(hours) as total_hours, COUNT(*) as days, "
            "SUM(payment) as total_payment "
            "FROM entries WHERE user_id = ? AND date LIKE ? AND project != '' "
            "GROUP BY project ORDER BY total_hours DESC",
            (user_id, f"{month_prefix}%"),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_month_budget(self, user_id: int, year: int, month: int) -> dict:
        month_prefix = f"{year:04d}-{month:02d}"
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT date, hours, start_time, end_time, note, project, payment "
            "FROM entries WHERE user_id = ? AND date LIKE ? ORDER BY date",
            (user_id, f"{month_prefix}%"),
        ).fetchall()
        entries = [dict(r) for r in rows]
        total_hours = sum(e["hours"] for e in entries)
        total_payment = sum(e.get("payment", 0) or 0 for e in entries)
        paid_days = sum(1 for e in entries if (e.get("payment", 0) or 0) > 0)
        unpaid_days = len(entries) - paid_days
        project_income: dict[str, float] = {}
        for e in entries:
            p = e.get("project", "") or "—"
            project_income.setdefault(p, 0)
            project_income[p] += e.get("payment", 0) or 0
        return {
            "entries": entries,
            "total_hours": total_hours,
            "total_payment": total_payment,
            "paid_days": paid_days,
            "unpaid_days": unpaid_days,
            "project_income": project_income,
        }

    def get_projects(self, user_id: int) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT project FROM entries WHERE user_id = ? AND project != '' "
            "ORDER BY project",
            (user_id,),
        ).fetchall()
        return [r["project"] for r in rows]

    def set_reminder(
        self, user_id: int, chat_id: int, enabled: bool, reminder_time: str = "19:00"
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO reminders (user_id, chat_id, enabled, reminder_time)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id=excluded.chat_id, enabled=excluded.enabled,
                reminder_time=excluded.reminder_time
            """,
            (user_id, chat_id, int(enabled), reminder_time),
        )
        conn.commit()

    def get_reminder(self, user_id: int) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM reminders WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_reminders(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM reminders WHERE enabled = 1"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_users_without_entry(self, date_str: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT r.user_id, r.chat_id, r.reminder_time
            FROM reminders r
            WHERE r.enabled = 1
            AND r.user_id NOT IN (
                SELECT user_id FROM entries WHERE date = ?
            )
            AND r.user_id NOT IN (
                SELECT user_id FROM reminder_log WHERE date = ?
            )
            """,
            (date_str, date_str),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_sent(self, user_id: int, date_str: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO reminder_log (user_id, date, sent_at) VALUES (?, ?, ?)",
            (user_id, date_str, datetime.now().isoformat()),
        )
        conn.commit()

    def is_reminder_sent(self, user_id: int, date_str: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM reminder_log WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        ).fetchone()
        return row is not None

    def set_admin(self, user_id: int, chat_id: int) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, chat_id) VALUES (?, ?)",
            (user_id, chat_id),
        )
        conn.commit()

    def is_admin(self, user_id: int) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None

    def remove_admin(self, user_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM admins WHERE user_id = ?", (user_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_all_admins(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM admins").fetchall()
        return [dict(r) for r in rows]

    def get_team_entries(
        self, date_from: str, date_to: str, project: str = None
    ) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT e.*, r.chat_id FROM entries e JOIN reminders r ON e.user_id = r.user_id WHERE e.date >= ? AND e.date <= ?"
        params: list = [date_from, date_to]
        if project:
            query += " AND e.project = ?"
            params.append(project)
        query += " ORDER BY e.date DESC, e.user_id"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_team_month_stats(self, year: int, month: int) -> list[dict]:
        month_prefix = f"{year:04d}-{month:02d}"
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT user_id, SUM(hours) as total_hours, COUNT(*) as days_worked,
                   AVG(hours) as avg_hours
            FROM entries
            WHERE date LIKE ?
            GROUP BY user_id
            ORDER BY total_hours DESC
            """,
            (f"{month_prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]
