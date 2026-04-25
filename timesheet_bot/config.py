import os
from dataclasses import dataclass


@dataclass
class Config:
    bot_token: str
    mini_app_url: str
    db_path: str
    reminder_check_interval: int = 60
    super_admin_id: int = 0
    webhook_url: str = ""
    webhook_secret: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "")
        if not token or token == "YOUR_BOT_TOKEN_HERE":
            raise ValueError("BOT_TOKEN env variable is required")
        return cls(
            bot_token=token,
            mini_app_url=os.getenv(
                "MINI_APP_URL", "https://your-domain.com/miniapp/index.html"
            ),
            db_path=os.getenv("DB_PATH", "timesheet.db"),
            reminder_check_interval=int(os.getenv("REMINDER_CHECK_INTERVAL", "60")),
            super_admin_id=int(os.getenv("SUPER_ADMIN_ID", "0")),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        )
