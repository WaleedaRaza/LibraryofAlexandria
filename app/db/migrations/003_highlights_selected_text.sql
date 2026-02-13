-- ============================================================================
-- MIGRATION 003: Update highlights table to use selected_text
-- Run this in Supabase SQL Editor
-- 
-- IMPORTANT: This replaces start_offset/end_offset with selected_text
-- Existing highlights will be lost (or need manual migration if you have data)
-- ============================================================================

-- Option 1: If you have NO existing highlights, just recreate the table:
DROP TABLE IF EXISTS chat_messages;  -- Has FK to highlights
DROP TABLE IF EXISTS annotations;     -- Has FK to highlights
DROP TABLE IF EXISTS highlights;

-- Recreate highlights with selected_text
CREATE TABLE highlights (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chapter_id      TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    selected_text   TEXT NOT NULL,
    color           TEXT DEFAULT 'yellow',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_highlights_user_id ON highlights(user_id);
CREATE INDEX idx_highlights_chapter_id ON highlights(chapter_id);

-- Recreate annotations
CREATE TABLE annotations (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL UNIQUE REFERENCES highlights(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_annotations_highlight_id ON annotations(highlight_id);

-- Recreate chat_messages
CREATE TABLE chat_messages (
    id              TEXT PRIMARY KEY,
    highlight_id    TEXT NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_messages_highlight_id ON chat_messages(highlight_id);
CREATE INDEX idx_chat_messages_created_at ON chat_messages(created_at);

-- Update schema version
INSERT INTO schema_versions (version, description) 
VALUES (3, 'Update highlights to use selected_text instead of offsets')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- Option 2: If you want to PRESERVE existing highlights (more complex)
-- Uncomment and run this instead of the above
-- ============================================================================
-- 
-- -- Add new column
-- ALTER TABLE highlights ADD COLUMN selected_text TEXT;
-- 
-- -- For each existing highlight, you'd need to extract text from book_text
-- -- This requires manual SQL or a script. Example placeholder:
-- -- UPDATE highlights 
-- -- SET selected_text = 'TODO: extract from book_text using offsets'
-- -- WHERE selected_text IS NULL;
-- 
-- -- Make it required
-- ALTER TABLE highlights ALTER COLUMN selected_text SET NOT NULL;
-- 
-- -- Drop old columns
-- ALTER TABLE highlights DROP COLUMN start_offset;
-- ALTER TABLE highlights DROP COLUMN end_offset;
