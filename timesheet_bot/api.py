from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from aiohttp import web

from .storage import StorageBase
from .utils import parse_shift_time

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    try:
        from urllib.parse import parse_qs

        data = parse_qs(init_data)
        hash_val = data.get("hash", [None])[0]
        if not hash_val:
            return None

        data.pop("hash", None)

        check_string = "\n".join(f"{k}={v[0]}" for k, v in sorted(data.items()))

        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()

        if computed_hash != hash_val:
            return None

        auth_date = int(data.get("auth_date", ["0"])[0])
        if time.time() - auth_date > max_age:
            return None

        result: dict = {}
        for key, values in data.items():
            if key == "user":
                result["user"] = json.loads(values[0])
            else:
                result[key] = values[0]

        return result
    except Exception:
        return None


class WebAppAPI:
    def __init__(self, storage: StorageBase, bot_token: str) -> None:
        self.storage = storage
        self.bot_token = bot_token
        self.app = web.Application(client_max_size=2 * 1024 * 1024)
        self.app.add_routes([
            web.get("/api/entries", self.get_entries),
            web.post("/api/entry", self.save_entry),
            web.delete("/api/entry", self.delete_entry),
            web.get("/api/health", self.health),
        ])

    def _get_user_id(self, request: web.Request) -> int | None:
        init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data")
        if not init_data:
            return None
        validated = validate_init_data(init_data, self.bot_token)
        if not validated:
            return None
        user = validated.get("user")
        if not user:
            return None
        return user.get("id")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def get_entries(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)

        date_from = request.query.get("date_from")
        date_to = request.query.get("date_to")
        entries = self.storage.get_entries(user_id, date_from=date_from, date_to=date_to)

        result: dict[str, dict] = {}
        for e in entries:
            result[e["date"]] = {
                "hours": e["hours"],
                "start_time": e.get("start_time", ""),
                "end_time": e.get("end_time", ""),
                "note": e.get("note", ""),
                "project": e.get("project", ""),
                "payment": e.get("payment", 0),
                "updated_at": e.get("updated_at", ""),
            }

        return web.json_response(result)

    async def save_entry(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        date_str = body.get("date")
        start_time = body.get("start_time", "")
        end_time = body.get("end_time", "")
        hours_raw = body.get("hours")

        if not date_str:
            return web.json_response({"error": "date required"}, status=400)

        if start_time and end_time:
            hours = parse_shift_time(start_time, end_time)
            if hours is None:
                return web.json_response({"error": "invalid start_time/end_time (use HH:MM)"}, status=400)
        elif hours_raw is not None:
            try:
                hours = float(hours_raw)
            except (ValueError, TypeError):
                return web.json_response({"error": "hours must be a number"}, status=400)
        else:
            return web.json_response({"error": "start_time+end_time or hours required"}, status=400)

        if hours <= 0 or hours > 24:
            return web.json_response({"error": "hours must be 0.5-24"}, status=400)

        note = body.get("note", "")
        project = body.get("project", "")
        payment = float(body.get("payment", 0))

        entry = self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, payment)
        logger.info(f"API save_entry: user={user_id} date={date_str} hours={hours}")
        return web.json_response({"ok": True, "entry": entry})

    async def delete_entry(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        date_str = body.get("date")
        if not date_str:
            return web.json_response({"error": "date required"}, status=400)

        deleted = self.storage.delete_entry(user_id, date_str)
        if deleted:
            logger.info(f"API delete_entry: user={user_id} date={date_str}")
        return web.json_response({"ok": deleted})
