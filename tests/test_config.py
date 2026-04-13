import os
from timesheet_bot.config import Config


class TestConfig:
    def test_from_env(self):
        os.environ["BOT_TOKEN"] = "test_token"
        config = Config.from_env()
        assert config.bot_token == "test_token"
        assert config.db_path == "timesheet.db"
        os.environ.pop("BOT_TOKEN", None)

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        with __import__("pytest").raises(ValueError, match="BOT_TOKEN"):
            Config.from_env()

    def test_default_token_raises(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
        with __import__("pytest").raises(ValueError, match="BOT_TOKEN"):
            Config.from_env()

    def test_custom_env(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "tok")
        monkeypatch.setenv("DB_PATH", "/data/bot.db")
        monkeypatch.setenv("REMINDER_CHECK_INTERVAL", "30")
        monkeypatch.setenv("SUPER_ADMIN_ID", "42")
        config = Config.from_env()
        assert config.db_path == "/data/bot.db"
        assert config.reminder_check_interval == 30
        assert config.super_admin_id == 42
