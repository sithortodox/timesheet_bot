from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta


def parse_project(text: str) -> tuple[str, str]:
    m = re.match(r"#(\S+)", text)
    if m:
        project = m.group(1)
        note = text[m.end():].strip()
        return project, note
    return "", text


def format_entry_line(entry: dict) -> str:
    proj = f" #{entry['project']}" if entry.get("project") else ""
    note = f" — {entry['note']}" if entry.get("note") else ""
    return f"• {entry['date']}: {entry['hours']}ч{proj}{note}"


def format_stats_header(title: str, days_worked: int, total_hours: float, avg_hours: float) -> list[str]:
    return [
        f"{title}\n",
        f"🗓 Рабочих дней: *{days_worked}*",
        f"⏱ Всего часов: *{total_hours:.1f}*",
        f"📈 Среднее в день: *{avg_hours:.1f} ч*\n",
    ]


class RateLimiter:
    def __init__(self, max_calls: int = 20, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self._calls: dict[int, list[datetime]] = defaultdict(list)

    def is_limited(self, user_id: int) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.period)
        self._calls[user_id] = [t for t in self._calls[user_id] if t > cutoff]
        if len(self._calls[user_id]) >= self.max_calls:
            return True
        self._calls[user_id].append(now)
        return False
