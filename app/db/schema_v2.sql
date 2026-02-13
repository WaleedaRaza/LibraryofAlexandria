-- ============================================================================
-- ALEXANDRIA LIBRARY DATABASE SCHEMA V2
-- Page-Anchored Knowledge Architecture
-- ============================================================================

-- ============================================================================
-- CORE: PAGE-ANCHORED TRUTH
-- ============================================================================

-- Book pages (ground truth anchors)
CREATE TABLE IF NOT EXISTS book_pages (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_number     INTEGER NOT NULL,
    page_text       TEXT,                    -- Extracted text for this page
    text_quality    REAL DEFAULT 0.5,        -- 0-1 quality score
    has_images      INTEGER DEFAULT 0,       -- Boolean
    is_scanned      INTEGER DEFAULT 0,       -- Boolean (OCR needed)
    word_count      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (book_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_book_pages_book_id ON book_pages(book_id);
CREATE INDEX IF NOT EXISTS idx_book_pages_page_number ON book_pages(page_number);

-- Page spans (precise anchors for highlights, citations, quotes)
CREATE TABLE IF NOT EXISTS page_spans (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    char_start      INTEGER,                 -- Character offset within page
    char_end        INTEGER,
    span_text       TEXT,                    -- The actual text in this span
    span_type       TEXT,                    -- 'highlight', 'citation', 'quote', 'landmark'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_page_spans_book_id ON page_spans(book_id);

-- Page chunks (for retrieval/embedding)
CREATE TABLE IF NOT EXISTS page_chunks (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    chunk_index     INTEGER,                 -- Order within book
    embedding       TEXT,                    -- JSON array or vector ref
    chunk_quality   REAL DEFAULT 0.5,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_page_chunks_book_id ON page_chunks(book_id);

-- ============================================================================
-- BOOK ARTIFACTS (Per-Book Intelligence)
-- ============================================================================

-- Master artifact record per book
CREATE TABLE IF NOT EXISTS book_artifacts (
    book_id         TEXT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    artifact_version INTEGER DEFAULT 1,
    bootstrap_status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'complete', 'failed'
    total_pages     INTEGER,
    structure_confidence REAL DEFAULT 0.0,
    last_bootstrap  TIMESTAMP,
    last_refinement TIMESTAMP,
    external_profile TEXT,                    -- JSON: author bio, canonical description, critiques
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Structure overlay (sections/chapters with page ranges)
CREATE TABLE IF NOT EXISTS book_sections (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    section_type    TEXT NOT NULL,           -- 'toc_real', 'toc_inferred', 'part', 'chapter', 'section'
    title           TEXT NOT NULL,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    parent_id       TEXT REFERENCES book_sections(id), -- For nested structure
    section_order   INTEGER,                 -- Order within parent
    confidence      REAL DEFAULT 0.5,
    provenance      TEXT,                    -- 'extracted_toc', 'heading_detection', 'llm_inference', 'user_confirmed'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_book_sections_book_id ON book_sections(book_id);

-- Landmarks (concepts, definitions, arguments, examples → page ranges)
CREATE TABLE IF NOT EXISTS book_landmarks (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    landmark_type   TEXT NOT NULL,           -- 'concept', 'definition', 'argument', 'example', 'counterpoint', 'conclusion'
    label           TEXT NOT NULL,           -- The concept/term name
    description     TEXT,                    -- Brief description
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    importance      REAL DEFAULT 0.5,        -- How central to the book
    confidence      REAL DEFAULT 0.5,
    provenance      TEXT,                    -- 'llm_bootstrap', 'user_highlight', 'interaction_derived'
    related_landmarks TEXT,                  -- JSON array of related landmark IDs
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_book_landmarks_book_id ON book_landmarks(book_id);
CREATE INDEX IF NOT EXISTS idx_book_landmarks_type ON book_landmarks(landmark_type);

-- Reading paths (goal-based navigation sequences)
CREATE TABLE IF NOT EXISTS book_paths (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    path_goal       TEXT NOT NULL,           -- 'understand_thesis', 'get_counterarguments', 'practical_takeaways'
    path_name       TEXT NOT NULL,
    steps           TEXT NOT NULL,           -- JSON array of {page_start, page_end, reason}
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_book_paths_book_id ON book_paths(book_id);

-- ============================================================================
-- USER INTERACTIONS (Page-Anchored)
-- ============================================================================

-- Page-anchored highlights (replaces old chapter-based highlights)
CREATE TABLE IF NOT EXISTS page_highlights (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    selected_text   TEXT NOT NULL,
    highlight_type  TEXT DEFAULT 'important', -- 'important', 'definition', 'disagree', 'insight', 'question'
    color           TEXT DEFAULT 'yellow',
    note            TEXT,
    is_public       INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_page_highlights_user_id ON page_highlights(user_id);
CREATE INDEX IF NOT EXISTS idx_page_highlights_book_id ON page_highlights(book_id);

-- Page-anchored chat threads
CREATE TABLE IF NOT EXISTS page_chats (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    scope_text      TEXT,                    -- The text being discussed
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page_chat_messages (
    id              TEXT PRIMARY KEY,
    chat_id         TEXT NOT NULL REFERENCES page_chats(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    page_citations  TEXT,                    -- JSON array of page numbers cited
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_page_chat_messages_chat_id ON page_chat_messages(chat_id);

-- Interaction events (for the compiler/flywheel)
CREATE TABLE IF NOT EXISTS interaction_events (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,                    -- Can be null for anonymous
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,           -- 'page_view', 'highlight', 'chat', 'jump', 'search_land'
    page_number     INTEGER,
    page_range_start INTEGER,
    page_range_end  INTEGER,
    query_context   TEXT,                    -- What query led here
    session_id      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_interaction_events_book_id ON interaction_events(book_id);
CREATE INDEX IF NOT EXISTS idx_interaction_events_type ON interaction_events(event_type);

-- Aggregated navigation priors (compiled from interactions)
CREATE TABLE IF NOT EXISTS navigation_priors (
    id              TEXT PRIMARY KEY,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    intent_pattern  TEXT NOT NULL,           -- e.g., 'definition_of_X', 'argument_about_Y'
    best_page_start INTEGER NOT NULL,
    best_page_end   INTEGER NOT NULL,
    confidence      REAL DEFAULT 0.5,
    sample_count    INTEGER DEFAULT 0,       -- How many interactions support this
    last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_navigation_priors_book_id ON navigation_priors(book_id);

-- ============================================================================
-- PUBLIC ANALYSIS LAYER
-- ============================================================================

CREATE TABLE IF NOT EXISTS public_analyses (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    analysis_type   TEXT NOT NULL,           -- 'summary', 'critique', 'connection', 'question'
    title           TEXT,
    content         TEXT NOT NULL,
    upvotes         INTEGER DEFAULT 0,
    is_verified     INTEGER DEFAULT 0,       -- Curator verified
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_public_analyses_book_id ON public_analyses(book_id);

-- ============================================================================
-- SCHEMA VERSION
-- ============================================================================

INSERT INTO schema_versions (version, description) 
VALUES (3, 'Page-anchored architecture with BookArtifacts')
ON CONFLICT (version) DO NOTHING;
