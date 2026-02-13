-- ============================================================================
-- MIGRATION 002: Add chat_messages table
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Chat messages tied to highlights (MANY messages per highlight)
-- Each highlight has its own conversation thread
CREATE TABLE IF NOT EXISTS chat_messages (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_highlight_id ON chat_messages(highlight_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

-- Update schema version
INSERT INTO schema_versions (version, description) 
VALUES (2, 'Add chat_messages table for highlight-tied conversations')
ON CONFLICT (version) DO NOTHING;
