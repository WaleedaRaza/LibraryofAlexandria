"""Revocable application sessions, compatible with Firebase Hosting's cookie proxy."""

import hashlib
import secrets
import time

from ..config import settings
from ..db.database import get_db, get_supabase, is_sqlite_mode


class SessionService:
    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, user_id: str, *, max_age: int | None = None) -> str:
        token = secrets.token_urlsafe(32)
        record = {"token_hash": self._hash(token), "user_id": user_id,
                  "expires_at": int(time.time()) + (max_age or settings.SESSION_MAX_AGE)}
        if is_sqlite_mode():
            db = get_db()
            with db:
                db.execute("DELETE FROM user_sessions WHERE expires_at<=?", (int(time.time()),))
                db.execute("INSERT INTO user_sessions (token_hash,user_id,expires_at) VALUES (:token_hash,:user_id,:expires_at)", record)
        else:
            database = get_supabase()
            database.table("user_sessions").delete().lte("expires_at", int(time.time())).execute()
            database.table("user_sessions").insert(record).execute()
        return token

    def user(self, token: str | None) -> dict | None:
        if not token or len(token) > 128:
            return None
        digest = self._hash(token)
        now = int(time.time())
        if is_sqlite_mode():
            row = get_db().execute(
                """SELECT u.id,u.email,u.display_name,u.username,u.avatar_key,u.role
                   FROM users u JOIN user_sessions s ON s.user_id=u.id
                   WHERE s.token_hash=? AND s.expires_at>?""", (digest, now)
            ).fetchone()
            return dict(row) if row else None
        sessions = get_supabase().table("user_sessions").select("user_id").eq(
            "token_hash", digest
        ).gt("expires_at", now).limit(1).execute().data or []
        if not sessions:
            return None
        users = get_supabase().table("users").select("id,email,display_name,username,avatar_key,role").eq(
            "id", sessions[0]["user_id"]
        ).limit(1).execute().data or []
        return users[0] if users else None

    def revoke(self, token: str | None) -> None:
        if not token or len(token) > 128:
            return
        digest = self._hash(token)
        if is_sqlite_mode():
            db = get_db()
            db.execute("DELETE FROM user_sessions WHERE token_hash=?", (digest,))
            db.commit()
        else:
            get_supabase().table("user_sessions").delete().eq("token_hash", digest).execute()
