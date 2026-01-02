"""
Alexandria Library - Database Connection
Supabase REST API (PostgREST) - No more connection string nightmares!

This module provides a clean interface to Supabase tables.
All queries go through HTTPS - no psycopg2, no poolers, no DNS issues.
"""

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator

from ..config import settings


# =============================================================================
# SUPABASE CLIENT
# =============================================================================

_supabase_client = None


def is_sqlite_mode() -> bool:
    """Check if we're in SQLite fallback mode (no Supabase configured)."""
    return not settings.SUPABASE_URL


def get_supabase():
    """Get the Supabase client (singleton)."""
    global _supabase_client
    
    if _supabase_client is None:
        from supabase import create_client
        
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_SERVICE_ROLE_KEY
        
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.\n"
                "Get these from: Supabase Dashboard → Settings → API"
            )
        
        _supabase_client = create_client(url, key)
        print(f"✅ Supabase client initialized (REST API)")
    
    return _supabase_client


def init_db():
    """Initialize database connection."""
    if is_sqlite_mode():
        _init_sqlite_db()
    else:
        _init_supabase_db()


def _init_supabase_db():
    """Verify Supabase is reachable and ensure test user exists."""
    try:
        client = get_supabase()
        # Quick ping - try to select from a table
        result = client.table("users").select("id").limit(1).execute()
        print("✅ Supabase connection verified")
        
        # Ensure anon test user exists for development
        try:
            existing = client.table("users").select("id").eq("id", "anon_test_user").execute()
            if not existing.data:
                client.table("users").insert({
                    "id": "anon_test_user",
                    "email": "anon@test.local",
                    "password_hash": "",
                    "display_name": "Anonymous",
                    "role": "user"
                }).execute()
                print("✅ Created anon_test_user")
        except Exception as e:
            print(f"⚠️  Could not ensure test user: {e}")
        
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        raise


def _init_sqlite_db():
    """Initialize SQLite database with schema."""
    schema_path = Path(__file__).parent / "schema.sql"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    conn = get_db()
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    
    # Create anonymous test user for development/testing
    conn.execute("""
        INSERT OR IGNORE INTO users (id, email, password_hash, display_name, role)
        VALUES ('anon_test_user', 'anon@test.local', '', 'Anonymous', 'user')
    """)
    
    conn.commit()
    print("✅ SQLite database initialized")


# =============================================================================
# COMPATIBILITY LAYER
# =============================================================================

class DictRow(dict):
    """Row that supports both dict and attribute access."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


# SQLite fallback for local development
_sqlite_connection: Optional[sqlite3.Connection] = None


def get_db():
    """
    Get database connection.
    
    In Supabase mode: returns the Supabase client
    In SQLite mode: returns SQLite connection
    """
    if is_sqlite_mode():
        global _sqlite_connection
        if _sqlite_connection is None:
            _sqlite_connection = sqlite3.connect(
                str(settings.DB_PATH), 
                check_same_thread=False
            )
            _sqlite_connection.row_factory = sqlite3.Row
            _sqlite_connection.execute("PRAGMA foreign_keys = ON")
        return _sqlite_connection
    else:
        return get_supabase()


def get_connection():
    """Get a database connection."""
    return get_db()


@contextmanager
def get_db_session() -> Generator[Any, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    if is_sqlite_mode():
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
    else:
        # Supabase doesn't need transactions for REST API
        yield get_supabase()
