#!/usr/bin/env python3
"""
Apply schema v2 (page-anchored architecture) to Supabase.

Usage:
    python -m admin.apply_schema_v2
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase


TABLES = [
    # Book pages
    """
    CREATE TABLE IF NOT EXISTS book_pages (
        id TEXT PRIMARY KEY,
        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL,
        page_text TEXT,
        text_quality REAL DEFAULT 0.5,
        has_images INTEGER DEFAULT 0,
        is_scanned INTEGER DEFAULT 0,
        word_count INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (book_id, page_number)
    )
    """,
    
    # Book artifacts master
    """
    CREATE TABLE IF NOT EXISTS book_artifacts (
        book_id TEXT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
        artifact_version INTEGER DEFAULT 1,
        bootstrap_status TEXT DEFAULT 'pending',
        total_pages INTEGER,
        structure_confidence REAL DEFAULT 0.0,
        last_bootstrap TIMESTAMP,
        last_refinement TIMESTAMP,
        external_profile TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Book sections
    """
    CREATE TABLE IF NOT EXISTS book_sections (
        id TEXT PRIMARY KEY,
        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        section_type TEXT NOT NULL,
        title TEXT NOT NULL,
        page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL,
        parent_id TEXT,
        section_order INTEGER,
        confidence REAL DEFAULT 0.5,
        provenance TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Book landmarks
    """
    CREATE TABLE IF NOT EXISTS book_landmarks (
        id TEXT PRIMARY KEY,
        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        landmark_type TEXT NOT NULL,
        label TEXT NOT NULL,
        description TEXT,
        page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL,
        importance REAL DEFAULT 0.5,
        confidence REAL DEFAULT 0.5,
        provenance TEXT,
        related_landmarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Book paths
    """
    CREATE TABLE IF NOT EXISTS book_paths (
        id TEXT PRIMARY KEY,
        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        path_goal TEXT NOT NULL,
        path_name TEXT NOT NULL,
        steps TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Interaction events
    """
    CREATE TABLE IF NOT EXISTS interaction_events (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        page_number INTEGER,
        page_range_start INTEGER,
        page_range_end INTEGER,
        query_context TEXT,
        session_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def apply_schema():
    print("=" * 60)
    print("APPLYING SCHEMA V2")
    print("=" * 60)
    
    init_db()
    client = get_supabase()
    
    # For Supabase, we need to use RPC or direct SQL
    # Since we can't run raw SQL, we'll just check if tables exist
    # and the tables should be created via Supabase dashboard or migrations
    
    print("\nNote: For Supabase, you need to apply the schema via the Supabase dashboard.")
    print("The SQL is in: app/db/schema_v2.sql")
    print("\nAlternatively, run these CREATE TABLE statements in the SQL editor.")
    
    # Check if tables exist by trying to query them
    tables_to_check = [
        "book_pages",
        "book_artifacts", 
        "book_sections",
        "book_landmarks",
        "book_paths",
        "interaction_events"
    ]
    
    print("\nChecking if tables exist:")
    for table in tables_to_check:
        try:
            result = client.table(table).select("*").limit(1).execute()
            print(f"  ✅ {table} - exists")
        except Exception as e:
            if "does not exist" in str(e) or "relation" in str(e).lower():
                print(f"  ❌ {table} - MISSING (create via Supabase dashboard)")
            else:
                print(f"  ⚠️ {table} - error: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    apply_schema()
