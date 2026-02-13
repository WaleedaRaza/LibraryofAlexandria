"""
Alexandria Library - Database Connection
SQLite-only for POC. Clean. No Supabase.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Any, Generator

from ..config import settings


# =============================================================================
# SQLITE CONNECTION
# =============================================================================

_connection: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    """Get the SQLite connection (singleton)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(
            str(settings.DB_PATH),
            check_same_thread=False
        )
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA foreign_keys = ON")
    return _connection


def init_db():
    """Initialize database from schema.sql and seed test user."""
    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    conn = get_db()
    with open(schema_path, "r") as f:
        conn.executescript(f.read())

    conn.execute("""
        INSERT OR IGNORE INTO users (id, email, password_hash, display_name, role)
        VALUES ('anon_test_user', 'anon@test.local', '', 'Anonymous', 'user')
    """)
    conn.commit()
    print("  Database initialized (SQLite)")


@contextmanager
def get_db_session() -> Generator[sqlite3.Connection, None, None]:
    """Context manager with automatic commit/rollback."""
    conn = sqlite3.connect(str(settings.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Legacy compatibility — some old code calls these
def is_sqlite_mode() -> bool:
    return True

def get_supabase():
    raise RuntimeError("Supabase is disabled in POC mode. Use get_db().")
