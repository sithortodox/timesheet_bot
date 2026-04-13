import pytest
from datetime import datetime
from timesheet_bot.storage import SqliteStorage


class TestSqliteStorageInit:
    def test_creates_tables(self, storage):
        assert storage is not None

    def test_in_memory(self):
        s = SqliteStorage(":memory:")
        entries = s.get_entries(123)
        assert entries == []


class TestSaveAndGetEntries:
    def test_save_and_get(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Работал")
        entries = storage.get_entries(123)
        assert len(entries) == 1
        assert entries[0]["date"] == "2025-04-10"
        assert entries[0]["hours"] == 8.0
        assert entries[0]["note"] == "Работал"

    def test_get_empty(self, storage):
        entries = storage.get_entries(999)
        assert entries == []

    def test_save_overwrites(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Первая")
        storage.save_entry(123, "2025-04-10", 6.0, "Вторая")
        entries = storage.get_entries(123)
        assert len(entries) == 1
        assert entries[0]["hours"] == 6.0
        assert entries[0]["note"] == "Вторая"

    def test_save_without_note(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        entries = storage.get_entries(123)
        assert entries[0]["note"] == ""

    def test_save_creates_updated_at(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        entries = storage.get_entries(123)
        assert entries[0]["updated_at"] is not None

    def test_multiple_entries(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-02", 7.5)
        storage.save_entry(123, "2025-04-03", 6.0)
        entries = storage.get_entries(123)
        assert len(entries) == 3

    def test_different_users_isolated(self, storage):
        storage.save_entry(1, "2025-04-10", 8.0, "User 1")
        storage.save_entry(2, "2025-04-10", 5.0, "User 2")
        assert storage.get_entries(1)[0]["hours"] == 8.0
        assert storage.get_entries(2)[0]["hours"] == 5.0

    def test_get_entries_date_filter(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-15", 7.5)
        storage.save_entry(123, "2025-05-01", 6.0)
        entries = storage.get_entries(123, date_from="2025-04-01", date_to="2025-04-30")
        assert len(entries) == 2

    def test_get_entries_limit(self, storage):
        for i in range(20):
            storage.save_entry(123, f"2025-04-{i+1:02d}", 8.0)
        entries = storage.get_entries(123, limit=5)
        assert len(entries) == 5

    def test_order_desc(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-10", 7.5)
        entries = storage.get_entries(123)
        assert entries[0]["date"] == "2025-04-10"


class TestDeleteEntry:
    def test_delete_existing(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        deleted = storage.delete_entry(123, "2025-04-10")
        assert deleted is True
        assert storage.get_entries(123) == []

    def test_delete_nonexistent(self, storage):
        deleted = storage.delete_entry(123, "2025-04-10")
        assert deleted is False

    def test_delete_wrong_user(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        deleted = storage.delete_entry(456, "2025-04-10")
        assert deleted is False


class TestMonthStats:
    def test_empty_month(self, storage):
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["entries"] == []
        assert stats["total_hours"] == 0
        assert stats["days_worked"] == 0
        assert stats["avg_hours"] == 0

    def test_with_entries(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "X")
        storage.save_entry(123, "2025-04-02", 7.5, "Y")
        storage.save_entry(123, "2025-04-03", 8.0, "")
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["days_worked"] == 3
        assert stats["total_hours"] == 23.5
        assert abs(stats["avg_hours"] - 7.833) < 0.01

    def test_other_month_excluded(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        storage.save_entry(123, "2025-05-10", 8.0)
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["days_worked"] == 1

    def test_other_user_excluded(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        storage.save_entry(456, "2025-04-10", 5.0)
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["days_worked"] == 1
        assert stats["total_hours"] == 8.0


class TestReminders:
    def test_set_reminder(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        r = storage.get_reminder(123)
        assert r["enabled"] == 1
        assert r["reminder_time"] == "19:00"

    def test_toggle_reminder(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.set_reminder(123, 123, False, "19:00")
        r = storage.get_reminder(123)
        assert r["enabled"] == 0

    def test_change_time(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.set_reminder(123, 123, True, "18:30")
        r = storage.get_reminder(123)
        assert r["reminder_time"] == "18:30"

    def test_get_reminder_none(self, storage):
        r = storage.get_reminder(999)
        assert r is None

    def test_get_all_reminders(self, storage):
        storage.set_reminder(1, 1, True, "19:00")
        storage.set_reminder(2, 2, True, "18:00")
        storage.set_reminder(3, 3, False, "20:00")
        reminders = storage.get_all_reminders()
        assert len(reminders) == 2


class TestReminderLog:
    def test_mark_and_check(self, storage):
        storage.mark_reminder_sent(123, "2025-04-10")
        assert storage.is_reminder_sent(123, "2025-04-10") is True
        assert storage.is_reminder_sent(123, "2025-04-11") is False

    def test_duplicate_mark(self, storage):
        storage.mark_reminder_sent(123, "2025-04-10")
        storage.mark_reminder_sent(123, "2025-04-10")
        assert storage.is_reminder_sent(123, "2025-04-10") is True

    def test_users_without_entry(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.set_reminder(456, 456, True, "19:00")
        storage.save_entry(123, "2025-04-10", 8.0)
        users = storage.get_users_without_entry("2025-04-10")
        user_ids = [u["user_id"] for u in users]
        assert 123 not in user_ids
        assert 456 in user_ids

    def test_already_reminded_excluded(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.mark_reminder_sent(123, "2025-04-10")
        users = storage.get_users_without_entry("2025-04-10")
        user_ids = [u["user_id"] for u in users]
        assert 123 not in user_ids
