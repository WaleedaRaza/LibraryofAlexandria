-- ============================================================================
-- ALEXANDRIA LIBRARY DATABASE SCHEMA
-- Version: 2.0 — Artifact-first architecture
--
-- INVARIANTS:
-- 1. Book text lives in artifact JSON on disk, NOT in the database
-- 2. Sections come from artifacts, NOT from a chapters table
-- 3. Highlights reference (book_id, section_id) — no FK to chapters
-- 4. SQLite is the primary store for POC
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================================
-- USERS (Minimal for V1)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL DEFAULT '',
    display_name    TEXT,
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (role IN ('user', 'admin'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================================
-- HIGHLIGHTS (Section-based, no FK to chapters)
-- ============================================================================

CREATE TABLE IF NOT EXISTS highlights (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    book_id         TEXT NOT NULL,          -- e.g. "metaphysics_aristotle"
    section_id      TEXT NOT NULL,          -- e.g. "sec_002"
    selected_text   TEXT NOT NULL,
    color           TEXT DEFAULT 'yellow',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_highlights_user_id ON highlights(user_id);
CREATE INDEX IF NOT EXISTS idx_highlights_book_section ON highlights(book_id, section_id);

-- ============================================================================
-- ANNOTATIONS (One per highlight)
-- ============================================================================

CREATE TABLE IF NOT EXISTS annotations (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL UNIQUE,
    text            TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (highlight_id) REFERENCES highlights(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_annotations_highlight_id ON annotations(highlight_id);

-- ============================================================================
-- CHAT MESSAGES (Tied to highlights — each highlight has a thread)
-- ============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (highlight_id) REFERENCES highlights(id) ON DELETE CASCADE,
    CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_highlight_id ON chat_messages(highlight_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

-- ============================================================================
-- SCHEMA VERSION
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_versions (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (10, 'V2 artifact-first schema — section highlights, no chapters table');
