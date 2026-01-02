-- ============================================================================
-- ALEXANDRIA LIBRARY DATABASE SCHEMA
-- Version: 1.0
-- 
-- INVARIANTS:
-- 1. Canon is singular - book_text.content is the source of truth
-- 2. Chapters reference offsets, they don't duplicate text
-- 3. file_path is admin/internal only - users read from book_text
-- 4. All state changes must be auditable
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================================
-- CANON (Immutable - Admin-only writes)
-- ============================================================================

-- Books in the library
CREATE TABLE IF NOT EXISTS books (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    author          TEXT NOT NULL,
    domain          TEXT,                   -- Philosophy, Strategy, Technology, etc.
    subdomain       TEXT,                   -- More specific categorization
    file_path       TEXT,                   -- Admin only: path to source PDF
    is_public       INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_domain ON books(domain);

-- Full text content (ONE entry per book - canon is singular)
CREATE TABLE IF NOT EXISTS book_text (
    book_id         TEXT PRIMARY KEY,
    content         TEXT NOT NULL,          -- Full text of the book
    word_count      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- Chapter boundaries (reference offsets, don't duplicate text)
CREATE TABLE IF NOT EXISTS chapters (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL,
    number          INTEGER NOT NULL,
    title           TEXT NOT NULL,
    start_offset    INTEGER NOT NULL,       -- Character offset into book_text.content
    end_offset      INTEGER NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE (book_id, number)
);

CREATE INDEX IF NOT EXISTS idx_chapters_book_id ON chapters(book_id);

-- ============================================================================
-- USERS (Minimal for V1)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,                   -- Optional
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (role IN ('user', 'admin'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================================
-- USER DATA (Private, Mutable)
-- ============================================================================

-- Books saved to personal library
CREATE TABLE IF NOT EXISTS saved_books (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    book_id         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE (user_id, book_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_books_user_id ON saved_books(user_id);

-- Text highlights
CREATE TABLE IF NOT EXISTS highlights (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    chapter_id      TEXT NOT NULL,
    start_offset    INTEGER NOT NULL,       -- Offset within chapter
    end_offset      INTEGER NOT NULL,
    color           TEXT DEFAULT 'yellow',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_highlights_user_id ON highlights(user_id);
CREATE INDEX IF NOT EXISTS idx_highlights_chapter_id ON highlights(chapter_id);

-- Annotations attached to highlights (ONE annotation per highlight)
CREATE TABLE IF NOT EXISTS annotations (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL UNIQUE,   -- One annotation per highlight
    text            TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (highlight_id) REFERENCES highlights(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_annotations_highlight_id ON annotations(highlight_id);

-- ============================================================================
-- GROWTH LOOP (Book Requests)
-- ============================================================================

CREATE TABLE IF NOT EXISTS book_requests (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    author          TEXT,
    reason          TEXT,                   -- Why do you want this book?
    status          TEXT NOT NULL DEFAULT 'PENDING',
    admin_notes     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'ADDED'))
);

CREATE INDEX IF NOT EXISTS idx_book_requests_user_id ON book_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_book_requests_status ON book_requests(status);

-- ============================================================================
-- SESSIONS (Signed cookie sessions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

-- ============================================================================
-- SCHEMA VERSION
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_versions (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_versions (version, description) 
VALUES (1, 'Initial schema - Alexandria v1.0');

