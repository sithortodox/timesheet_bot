from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_shift_time(start_str: str, end_str: str) -> float | None:
    m1 = _TIME_RE.match(start_str.strip())
    m2 = _TIME_RE.match(end_str.strip())
    if not m1 or not m2:
        return None
    sh, sm = int(m1.group(1)), int(m1.group(2))
    eh, em = int(m2.group(1)), int(m2.group(2))
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
        return None
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    diff = end_min - start_min
    if diff <= 0:
        return None
    hours = diff / 60
    if hours > 24:
        return None
    return hours


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
    shift = ""
    if entry.get("start_time") and entry.get("end_time"):
        shift = f" {entry['start_time']}-{entry['end_time']}"
    return f"• {entry['date']}: {entry['hours']}ч{shift}{proj}{note}"


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
