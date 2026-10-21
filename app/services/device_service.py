"""Pairing a reading device (the Kindle) with an account, without typing a password on e-ink.

The device asks for a short code and shows it. The reader enters the code at /device while
signed in on any browser. The device polls with the code and a secret it alone knows, and
receives a long-lived session token. Tokens are ordinary revocable sessions, so signing out of
all devices from the account page cuts the Kindle off too.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from ..db.database import get_db, get_supabase, is_sqlite_mode
from .session_service import SessionService

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I; what people can read on a screen and type
CODE_LENGTH = 6
CODE_TTL_SECONDS = 10 * 60
DEVICE_TOKEN_MAX_AGE = 365 * 24 * 60 * 60


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def format_code(code: str) -> str:
    code = code.upper().replace("-", "").replace(" ", "")
    return f"{code[:3]}-{code[3:]}" if len(code) == CODE_LENGTH else code


def normalize_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch in CODE_ALPHABET)[:CODE_LENGTH]


class DeviceService:
    def create_code(self, device_name: str) -> dict:
        now = int(time.time())
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        secret = secrets.token_urlsafe(24)
        record = {
            "code": code,
            "secret_hash": _hash(secret),
            "device_name": (device_name or "Kindle").strip()[:60] or "Kindle",
            "created_at": now,
            "expires_at": now + CODE_TTL_SECONDS,
            "token": None,
        }
        if is_sqlite_mode():
            db = get_db()
            with db:
                db.execute("DELETE FROM device_codes WHERE expires_at<=?", (now,))
                db.execute("DELETE FROM device_codes WHERE code=?", (code,))
                db.execute(
                    "INSERT INTO device_codes (code,secret_hash,device_name,created_at,expires_at) VALUES (?,?,?,?,?)",
                    (code, record["secret_hash"], record["device_name"], now, record["expires_at"]),
                )
        else:
            database = get_supabase()
            database.table("device_codes").delete().lte("expires_at", now).execute()
            database.table("device_codes").delete().eq("code", code).execute()
            database.table("device_codes").insert({key: record[key] for key in ("code", "secret_hash", "device_name", "created_at", "expires_at")}).execute()
        return {"code": code, "secret": secret, "expires_in": CODE_TTL_SECONDS, "device_name": record["device_name"]}

    def _row(self, code: str) -> dict | None:
        now = int(time.time())
        if is_sqlite_mode():
            row = get_db().execute("SELECT * FROM device_codes WHERE code=? AND expires_at>?", (code, now)).fetchone()
            return dict(row) if row else None
        rows = get_supabase().table("device_codes").select("*").eq("code", code).gt("expires_at", now).limit(1).execute().data or []
        return rows[0] if rows else None

    def pending(self, code: str) -> dict | None:
        """The code a signed-in reader is about to claim, if it is still open."""
        row = self._row(normalize_code(code))
        if not row or row.get("claimed_token"):
            return None
        return {"code": row["code"], "device_name": row["device_name"]}

    def claim(self, code: str, user: dict) -> bool:
        """Attach the reader's account to the device code. The device collects the token on its next poll."""
        row = self._row(normalize_code(code))
        if not row or row.get("claimed_token"):
            return False
        token = SessionService().create(user["id"], max_age=DEVICE_TOKEN_MAX_AGE)
        if is_sqlite_mode():
            db = get_db()
            with db:
                changed = db.execute("UPDATE device_codes SET claimed_token=?, user_id=? WHERE code=? AND claimed_token IS NULL",
                                     (token, user["id"], row["code"]))
                return changed.rowcount == 1
        result = get_supabase().table("device_codes").update({"claimed_token": token, "user_id": user["id"]}).eq(
            "code", row["code"]).is_("claimed_token", "null").execute()
        return bool(result.data)

    def poll(self, code: str, secret: str) -> dict:
        """Called by the device. Hands the token over exactly once, then forgets the code."""
        row = self._row(normalize_code(code))
        if not row or not secrets.compare_digest(row["secret_hash"], _hash(secret or "")):
            return {"status": "expired"}
        if not row.get("claimed_token"):
            return {"status": "pending"}
        token = row["claimed_token"]
        if is_sqlite_mode():
            db = get_db()
            with db:
                db.execute("DELETE FROM device_codes WHERE code=?", (row["code"],))
        else:
            get_supabase().table("device_codes").delete().eq("code", row["code"]).execute()
        user = SessionService().user(token) or {}
        return {"status": "claimed", "token": token, "user": {"display_name": user.get("display_name", "Reader")}}
