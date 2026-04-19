from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
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
        self.app = web.Application(client_max_size=10 * 1024 * 1024)
        self.app.add_routes([
            web.get("/api/entries", self.get_entries),
            web.post("/api/entry", self.save_entry),
            web.delete("/api/entry", self.delete_entry),
            web.get("/api/income", self.get_income),
            web.post("/api/income", self.save_income),
            web.delete("/api/income", self.delete_income),
            web.get("/api/photos", self.get_photos),
            web.post("/api/photos", self.upload_photo),
            web.delete("/api/photos", self.delete_photo),
            web.get("/api/photo/{photo_id}", self.serve_photo),
            web.get("/api/projects", self.get_projects),
            web.get("/api/health", self.health),
        ])

    def _get_user_id(self, request: web.Request) -> int | None:
        init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("init_data")
        if init_data:
            validated = validate_init_data(init_data, self.bot_token)
            if validated:
                user = validated.get("user")
                if user:
                    return user.get("id")
            logger.info(f"init_data validation failed for user_id header check")
        uid_header = request.headers.get("X-Telegram-User-Id") or request.query.get("user_id")
        if uid_header:
            try:
                return int(uid_header)
            except (ValueError, TypeError):
                pass
        return None

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
                "day_type": e.get("day_type", "work"),
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
        project = body.get("project", "").lower()
        payment = float(body.get("payment", 0))
        day_type = body.get("day_type", "work")
        if day_type not in ("work", "dayoff"):
            day_type = "work"

        entry = self.storage.save_entry(user_id, date_str, hours, note, project, start_time, end_time, payment, day_type)
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

    async def get_income(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        date_from = request.query.get("date_from")
        date_to = request.query.get("date_to")
        items = self.storage.get_income(user_id, date_from=date_from, date_to=date_to)
        return web.json_response(items)

    async def save_income(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        date_str = body.get("date")
        amount = body.get("amount")
        if not date_str or amount is None:
            return web.json_response({"error": "date and amount required"}, status=400)
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return web.json_response({"error": "amount must be a number"}, status=400)
        if amount <= 0:
            return web.json_response({"error": "amount must be positive"}, status=400)
        note = body.get("note", "")
        result = self.storage.save_income(user_id, date_str, amount, note)
        logger.info(f"API save_income: user={user_id} date={date_str} amount={amount}")
        return web.json_response({"ok": True, "income": result})

    async def delete_income(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        income_id = body.get("id")
        if income_id is None:
            return web.json_response({"error": "id required"}, status=400)
        deleted = self.storage.delete_income(user_id, int(income_id))
        return web.json_response({"ok": deleted})

    async def get_photos(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        date_str = request.query.get("date")
        if not date_str:
            return web.json_response({"error": "date required"}, status=400)
        photos = self.storage.get_photos(user_id, date_str)
        for p in photos:
            p["url"] = f"/api/photo/{p['id']}"
        return web.json_response(photos)

    async def upload_photo(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"error": "multipart required"}, status=400)

        date_str = None
        caption = ""
        file_data = None
        file_name = None

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "date":
                date_str = (await part.text()).strip()
            elif part.name == "caption":
                caption = (await part.text()).strip()
            elif part.name == "file":
                file_data = await part.read()
                fn = part.filename or "photo.jpg"
                ext = os.path.splitext(fn)[1] or ".jpg"
                file_name = f"{uuid.uuid4().hex}{ext}"

        if not date_str or not file_data:
            return web.json_response({"error": "date and file required"}, status=400)

        if len(file_data) > 10 * 1024 * 1024:
            return web.json_response({"error": "file too large (max 10MB)"}, status=400)

        photo_dir = os.path.join("/app/data/photos", str(user_id), date_str)
        os.makedirs(photo_dir, exist_ok=True)
        file_path = os.path.join(photo_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(file_data)

        result = self.storage.save_photo(user_id, date_str, file_name, caption=caption)
        result["url"] = f"/api/photo/{result['id']}"
        logger.info(f"API upload_photo: user={user_id} date={date_str} file={file_name}")
        return web.json_response({"ok": True, "photo": result})

    async def delete_photo(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        photo_id = body.get("id")
        if photo_id is None:
            return web.json_response({"error": "id required"}, status=400)
        photo = self.storage.get_photo(int(photo_id))
        if not photo or photo["user_id"] != user_id:
            return web.json_response({"error": "not found"}, status=404)
        deleted = self.storage.delete_photo(user_id, int(photo_id))
        if deleted:
            file_path = os.path.join("/app/data/photos", str(user_id), photo["date"], photo["file_name"])
            try:
                os.remove(file_path)
            except OSError:
                pass
        return web.json_response({"ok": deleted})

    async def serve_photo(self, request: web.Request) -> web.Response:
        photo_id = int(request.match_info["photo_id"])
        photo = self.storage.get_photo(photo_id)
        if not photo:
            return web.json_response({"error": "not found"}, status=404)
        user_id = self._get_user_id(request)
        if user_id is None or photo["user_id"] != user_id:
            return web.json_response({"error": "unauthorized"}, status=401)
        file_path = os.path.join("/app/data/photos", str(photo["user_id"]), photo["date"], photo["file_name"])
        if not os.path.exists(file_path):
            return web.json_response({"error": "file not found"}, status=404)
        ext = os.path.splitext(photo["file_name"])[1].lower()
        content_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp",
        }
        ct = content_types.get(ext, "application/octet-stream")
        return web.FileResponse(file_path, headers={"Content-Type": ct})

    async def get_projects(self, request: web.Request) -> web.Response:
        user_id = self._get_user_id(request)
        if user_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        projects = self.storage.get_projects(user_id)
        return web.json_response(projects)
