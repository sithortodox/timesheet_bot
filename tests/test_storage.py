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
        s.close()


class TestSaveAndGetEntries:
    def test_save_and_get(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Работал")
        entries = storage.get_entries(123)
        assert len(entries) == 1
        assert entries[0]["hours"] == 8.0
        assert entries[0]["note"] == "Работал"

    def test_get_empty(self, storage):
        assert storage.get_entries(999) == []

    def test_save_overwrites(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Первая")
        storage.save_entry(123, "2025-04-10", 6.0, "Вторая")
        assert storage.get_entries(123)[0]["hours"] == 6.0

    def test_save_without_note(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        assert storage.get_entries(123)[0]["note"] == ""

    def test_save_creates_updated_at(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        assert storage.get_entries(123)[0]["updated_at"] is not None

    def test_multiple_entries(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-02", 7.5)
        storage.save_entry(123, "2025-04-03", 6.0)
        assert len(storage.get_entries(123)) == 3

    def test_different_users_isolated(self, storage):
        storage.save_entry(1, "2025-04-10", 8.0, "U1")
        storage.save_entry(2, "2025-04-10", 5.0, "U2")
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
        assert len(storage.get_entries(123, limit=5)) == 5

    def test_order_desc(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(123, "2025-04-10", 7.5)
        assert storage.get_entries(123)[0]["date"] == "2025-04-10"


class TestProjectEntries:
    def test_save_with_project(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "API ревью", "backend")
        assert storage.get_entries(123)[0]["project"] == "backend"

    def test_save_without_project(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0, "Работал")
        assert storage.get_entries(123)[0]["project"] == ""

    def test_filter_by_project(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "A", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "B", "design")
        storage.save_entry(123, "2025-04-03", 6.0, "C", "")
        assert len(storage.get_entries(123, project="backend")) == 1

    def test_get_projects(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "", "design")
        storage.save_entry(123, "2025-04-03", 6.0, "", "backend")
        assert set(storage.get_projects(123)) == {"backend", "design"}

    def test_get_projects_empty(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "Без проекта")
        assert storage.get_projects(123) == []

    def test_project_stats(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "", "backend")
        storage.save_entry(123, "2025-04-03", 6.0, "", "design")
        stats = storage.get_project_stats(123, 2025, 4)
        backend = [s for s in stats if s["project"] == "backend"][0]
        assert backend["total_hours"] == 15.0
        assert backend["days"] == 2

    def test_month_stats_project_filter(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "", "design")
        stats = storage.get_month_stats(123, 2025, 4, project="backend")
        assert stats["days_worked"] == 1
        assert stats["total_hours"] == 8.0


class TestDeleteEntry:
    def test_delete_existing(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        assert storage.delete_entry(123, "2025-04-10") is True
        assert storage.get_entries(123) == []

    def test_delete_nonexistent(self, storage):
        assert storage.delete_entry(123, "2025-04-10") is False

    def test_delete_wrong_user(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        assert storage.delete_entry(456, "2025-04-10") is False


class TestMonthStats:
    def test_empty_month(self, storage):
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["entries"] == []
        assert stats["total_hours"] == 0

    def test_with_entries(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0, "X")
        storage.save_entry(123, "2025-04-02", 7.5, "Y")
        storage.save_entry(123, "2025-04-03", 8.0, "")
        stats = storage.get_month_stats(123, 2025, 4)
        assert stats["days_worked"] == 3
        assert stats["total_hours"] == 23.5

    def test_other_month_excluded(self, storage):
        storage.save_entry(123, "2025-04-10", 8.0)
        storage.save_entry(123, "2025-05-10", 8.0)
        assert storage.get_month_stats(123, 2025, 4)["days_worked"] == 1


class TestWeekStats:
    def test_empty_week(self, storage):
        stats = storage.get_week_stats(123, "2025-04-07", "2025-04-13")
        assert stats["entries"] == []
        assert stats["total_hours"] == 0

    def test_with_entries(self, storage):
        storage.save_entry(123, "2025-04-07", 8.0)
        storage.save_entry(123, "2025-04-08", 7.5)
        storage.save_entry(123, "2025-04-09", 6.0)
        stats = storage.get_week_stats(123, "2025-04-07", "2025-04-13")
        assert stats["days_worked"] == 3
        assert stats["total_hours"] == 21.5

    def test_out_of_range_excluded(self, storage):
        storage.save_entry(123, "2025-04-06", 8.0)
        storage.save_entry(123, "2025-04-07", 7.5)
        stats = storage.get_week_stats(123, "2025-04-07", "2025-04-13")
        assert stats["days_worked"] == 1


class TestReminders:
    def test_set_reminder(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        r = storage.get_reminder(123)
        assert r["enabled"] == 1
        assert r["reminder_time"] == "19:00"

    def test_toggle_reminder(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.set_reminder(123, 123, False, "19:00")
        assert storage.get_reminder(123)["enabled"] == 0

    def test_get_reminder_none(self, storage):
        assert storage.get_reminder(999) is None

    def test_get_all_reminders(self, storage):
        storage.set_reminder(1, 1, True, "19:00")
        storage.set_reminder(2, 2, True, "18:00")
        storage.set_reminder(3, 3, False, "20:00")
        assert len(storage.get_all_reminders()) == 2


class TestReminderLog:
    def test_mark_and_check(self, storage):
        storage.mark_reminder_sent(123, "2025-04-10")
        assert storage.is_reminder_sent(123, "2025-04-10") is True
        assert storage.is_reminder_sent(123, "2025-04-11") is False

    def test_users_without_entry(self, storage):
        storage.set_reminder(123, 123, True, "19:00")
        storage.set_reminder(456, 456, True, "19:00")
        storage.save_entry(123, "2025-04-10", 8.0)
        users = storage.get_users_without_entry("2025-04-10")
        user_ids = [u["user_id"] for u in users]
        assert 123 not in user_ids
        assert 456 in user_ids


class TestAdmins:
    def test_set_and_check(self, storage):
        storage.set_admin(123, 123)
        assert storage.is_admin(123) is True
        assert storage.is_admin(456) is False

    def test_remove(self, storage):
        storage.set_admin(123, 123)
        assert storage.remove_admin(123) is True
        assert storage.is_admin(123) is False

    def test_remove_nonexistent(self, storage):
        assert storage.remove_admin(999) is False

    def test_get_all_admins(self, storage):
        storage.set_admin(1, 1)
        storage.set_admin(2, 2)
        assert len(storage.get_all_admins()) == 2

    def test_duplicate_ignored(self, storage):
        storage.set_admin(123, 123)
        storage.set_admin(123, 456)
        assert len(storage.get_all_admins()) == 1


class TestTeamStats:
    def test_team_month_stats(self, storage):
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(456, "2025-04-01", 7.0)
        storage.save_entry(456, "2025-04-02", 6.0)
        stats = storage.get_team_month_stats(2025, 4)
        assert len(stats) == 2

    def test_team_entries(self, storage):
        storage.set_reminder(123, 123, True)
        storage.set_reminder(456, 456, True)
        storage.save_entry(123, "2025-04-01", 8.0)
        storage.save_entry(456, "2025-04-01", 7.0)
        entries = storage.get_team_entries("2025-04-01", "2025-04-30")
        assert len(entries) == 2

    def test_team_entries_project_filter(self, storage):
        storage.set_reminder(123, 123, True)
        storage.save_entry(123, "2025-04-01", 8.0, "", "backend")
        storage.save_entry(123, "2025-04-02", 7.0, "", "design")
        entries = storage.get_team_entries("2025-04-01", "2025-04-30", project="backend")
        assert len(entries) == 1
