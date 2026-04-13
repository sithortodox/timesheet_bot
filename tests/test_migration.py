import json
import os
import sqlite3
import tempfile
from migrate_json_to_sqlite import migrate


class TestMigration:
    def test_migrate_basic(self, tmp_path):
        json_path = str(tmp_path / "data.json")
        db_path = str(tmp_path / "test.db")

        data = {
            "123": {
                "entries": {
                    "2025-04-01": {"hours": 8, "note": "Работал", "updated_at": "2025-04-01T18:00"},
                    "2025-04-02": {"hours": 7.5, "note": "Встречи", "updated_at": "2025-04-02T18:00"},
                }
            },
            "456": {
                "entries": {
                    "2025-04-01": {"hours": 6, "note": "", "updated_at": "2025-04-01T17:00"},
                }
            },
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        migrate(json_path, db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM entries ORDER BY user_id, date").fetchall()
        assert len(rows) == 3
        assert rows[0]["user_id"] == 123
        assert rows[0]["hours"] == 8.0
        assert rows[2]["user_id"] == 456
        conn.close()

    def test_migrate_missing_file(self, tmp_path, capsys):
        migrate(str(tmp_path / "nonexistent.json"), str(tmp_path / "test.db"))
        captured = capsys.readouterr()
        assert "не найден" in captured.out

    def test_migrate_preserves_notes(self, tmp_path):
        json_path = str(tmp_path / "data.json")
        db_path = str(tmp_path / "test.db")

        data = {"1": {"entries": {"2025-04-01": {"hours": 8, "note": "Привет мир", "updated_at": "x"}}}}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        migrate(json_path, db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM entries").fetchone()
        assert row["note"] == "Привет мир"
        conn.close()
