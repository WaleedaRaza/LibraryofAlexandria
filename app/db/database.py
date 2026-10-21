"""Database access with SQLite development and Supabase production modes."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from ..config import settings

_sqlite_connection: Optional[sqlite3.Connection] = None
_supabase_client = None


def is_sqlite_mode() -> bool:
    return not bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client

        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Supabase production credentials are not configured")
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


def get_db() -> Any:
    if not is_sqlite_mode():
        return get_supabase()
    global _sqlite_connection
    if _sqlite_connection is None:
        _sqlite_connection = sqlite3.connect(str(settings.DB_PATH), check_same_thread=False)
        _sqlite_connection.row_factory = sqlite3.Row
        _sqlite_connection.execute("PRAGMA foreign_keys = ON")
    return _sqlite_connection


def init_db() -> None:
    if not is_sqlite_mode():
        # Fail early on an unapplied release migration, rather than on a reader's first action.
        required = {"users": "id,username,avatar_key,role", "user_sessions": "token_hash,expires_at",
                    "saved_books": "id,status", "book_submissions": "id,status",
                    "community_editions": "id,book_json", "submission_reviews": "id,source_ids_json",
                    "source_jobs": "id,status,completed", "source_job_items": "id,status,candidates_json",
                    "reading_companion_messages": "id,user_id,role,sources_json"}
        for table, columns in required.items():
            get_supabase().table(table).select(columns).limit(1).execute()
        return
    schema_path = Path(__file__).parent / "schema.sql"
    connection = get_db()
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if "username" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "avatar_key" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN avatar_key TEXT")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL"
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_books)")}
    if "status" not in columns:
        connection.execute(
            "ALTER TABLE saved_books ADD COLUMN status TEXT NOT NULL DEFAULT 'want_to_read' "
            "CHECK (status IN ('want_to_read', 'reading', 'read'))"
        )
        connection.execute(
            """UPDATE saved_books SET status = CASE
                WHEN (SELECT percent FROM reading_progress p WHERE p.user_id = saved_books.user_id
                      AND p.book_id = saved_books.book_id) >= 100 THEN 'read'
                WHEN EXISTS (SELECT 1 FROM reading_progress p WHERE p.user_id = saved_books.user_id
                      AND p.book_id = saved_books.book_id) THEN 'reading'
                ELSE 'want_to_read' END"""
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_saved_books_status "
        "ON saved_books(user_id, status, created_at)"
    )
    connection.commit()


@contextmanager
def get_db_session() -> Generator[Any, None, None]:
    if not is_sqlite_mode():
        yield get_supabase()
        return
    connection = sqlite3.connect(str(settings.DB_PATH), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
