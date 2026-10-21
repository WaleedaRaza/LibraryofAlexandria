PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL,
    username TEXT,
    avatar_key TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_books (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'want_to_read' CHECK (status IN ('want_to_read', 'reading', 'read')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS reading_progress (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    page_count INTEGER,
    percent REAL NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS highlights (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    selected_text TEXT NOT NULL,
    text_start INTEGER,
    text_end INTEGER,
    color TEXT NOT NULL DEFAULT 'gold',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    highlight_id TEXT NOT NULL UNIQUE REFERENCES highlights(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    highlight_id TEXT NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_saved_books_user ON saved_books(user_id);
CREATE INDEX IF NOT EXISTS idx_progress_user ON reading_progress(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_highlights_user ON highlights(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_highlights_book ON highlights(book_id, page_number);
CREATE INDEX IF NOT EXISTS idx_chat_highlight ON chat_messages(highlight_id, created_at);

CREATE TABLE IF NOT EXISTS reading_companion_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reading_companion_user
    ON reading_companion_messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS contributions (
    id TEXT PRIMARY KEY,
    contributor_key TEXT NOT NULL,
    contributor_name TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    destination TEXT NOT NULL CHECK (destination IN ('shared', 'vault')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'private')),
    original_filename TEXT NOT NULL,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contributions_owner ON contributions(contributor_key, created_at);

CREATE TABLE IF NOT EXISTS book_submissions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    links_json TEXT NOT NULL DEFAULT '[]',
    files_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_book_submissions_user ON book_submissions(user_id, created_at);

CREATE TABLE IF NOT EXISTS community_editions (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES book_submissions(id),
    book_json TEXT NOT NULL,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS submission_reviews (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES book_submissions(id),
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'declined')),
    note TEXT NOT NULL,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_submission_reviews_submission ON submission_reviews(submission_id, created_at);

CREATE TABLE IF NOT EXISTS source_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'complete', 'cancelled')),
    total INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_job_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES source_jobs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'complete', 'failed', 'cancelled')),
    candidates_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, position)
);
CREATE INDEX IF NOT EXISTS idx_source_jobs_user ON source_jobs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_source_job_items_job ON source_job_items(job_id, position);

CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (20, 'Waleeds Library: catalog, progress, PDF highlights, reading memory');
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (21, 'LibXNDR: explicit personal shelf status');
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (22, 'LibXNDR: editable reader profiles');
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (23, 'LibXNDR: revocable sessions and private submission review');
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (24, 'LibXNDR: durable reader source-finder jobs');
INSERT OR IGNORE INTO schema_versions (version, description)
VALUES (25, 'LibXNDR: private citation-backed reading companion');
