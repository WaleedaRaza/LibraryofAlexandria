-- Run once in the Supabase SQL editor. Private user uploads remain in the
-- `waleeds-library` bucket; the reviewed founding collection is served from GCS.

CREATE TABLE IF NOT EXISTS public.users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    username TEXT,
    avatar_key TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS avatar_key TEXT;
-- Legacy Alexandria accounts stored local password hashes. Production auth now
-- lives in Supabase Auth, so newly mirrored profiles must not need that column.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'password_hash'
    ) THEN
        ALTER TABLE public.users ALTER COLUMN password_hash DROP NOT NULL;
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON public.users (lower(username)) WHERE username IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON public.user_sessions(user_id);
ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.saved_books (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'want_to_read' CHECK (status IN ('want_to_read', 'reading', 'read')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, book_id)
);

-- Older Alexandra installs tied reading state to the legacy relational canon.
-- LibXNDR's public canon is the versioned catalog in the application image, so
-- user state must be able to reference those stable catalog IDs directly.
ALTER TABLE public.saved_books DROP CONSTRAINT IF EXISTS saved_books_book_id_fkey;

CREATE TABLE IF NOT EXISTS public.reading_progress (
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    page_count INTEGER,
    percent DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, book_id)
);
ALTER TABLE public.reading_progress DROP CONSTRAINT IF EXISTS reading_progress_book_id_fkey;

-- Existing projects get the column without losing saves or page progress.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'saved_books' AND column_name = 'status'
    ) THEN
        ALTER TABLE public.saved_books ADD COLUMN status TEXT NOT NULL DEFAULT 'want_to_read'
            CHECK (status IN ('want_to_read', 'reading', 'read'));
        UPDATE public.saved_books AS saved SET status = CASE
            WHEN progress.percent >= 100 THEN 'read' ELSE 'reading' END
        FROM public.reading_progress AS progress
        WHERE progress.user_id = saved.user_id AND progress.book_id = saved.book_id;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.highlights (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    selected_text TEXT NOT NULL,
    text_start INTEGER,
    text_end INTEGER,
    color TEXT NOT NULL DEFAULT 'gold',
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.highlights ADD COLUMN IF NOT EXISTS book_id TEXT;
ALTER TABLE public.highlights ADD COLUMN IF NOT EXISTS page_number INTEGER;
ALTER TABLE public.highlights ADD COLUMN IF NOT EXISTS text_start INTEGER;
ALTER TABLE public.highlights ADD COLUMN IF NOT EXISTS text_end INTEGER;
ALTER TABLE public.highlights DROP CONSTRAINT IF EXISTS highlights_book_id_fkey;
ALTER TABLE public.highlights DROP CONSTRAINT IF EXISTS highlights_chapter_id_fkey;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'highlights' AND column_name = 'chapter_id'
    ) THEN
        ALTER TABLE public.highlights ALTER COLUMN chapter_id DROP NOT NULL;
    END IF;
END $$;
UPDATE public.highlights SET book_id = '' WHERE book_id IS NULL;
UPDATE public.highlights SET page_number = 1 WHERE page_number IS NULL;
ALTER TABLE public.highlights ALTER COLUMN book_id SET NOT NULL;
ALTER TABLE public.highlights ALTER COLUMN page_number SET NOT NULL;

CREATE TABLE IF NOT EXISTS public.annotations (
    id TEXT PRIMARY KEY,
    highlight_id TEXT NOT NULL UNIQUE REFERENCES public.highlights(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id TEXT PRIMARY KEY,
    highlight_id TEXT NOT NULL REFERENCES public.highlights(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- The catalog lives in library/catalog.json, not a books table. Drop legacy
-- Alexandria foreign keys that make saving/progress/highlights fail with 23503.
DO $$
DECLARE fk RECORD;
BEGIN
    FOR fk IN
        SELECT conrelid::regclass AS tbl, conname
        FROM pg_constraint
        WHERE contype = 'f'
          AND confrelid = 'public.books'::regclass
          AND conrelid::regclass::text IN
              ('saved_books','reading_progress','highlights','public.saved_books','public.reading_progress','public.highlights')
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', fk.tbl, fk.conname);
    END LOOP;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_saved_books_user ON public.saved_books(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_books_status ON public.saved_books(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_progress_user ON public.reading_progress(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_highlights_user ON public.highlights(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_highlights_book ON public.highlights(book_id, page_number);
CREATE INDEX IF NOT EXISTS idx_chat_highlight ON public.chat_messages(highlight_id, created_at);

CREATE TABLE IF NOT EXISTS public.reading_companion_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reading_companion_user
    ON public.reading_companion_messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS public.book_submissions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    files_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined')),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_book_submissions_user ON public.book_submissions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.community_editions (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES public.book_submissions(id),
    book_json JSONB NOT NULL,
    published_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.submission_reviews (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES public.book_submissions(id),
    reviewer_id TEXT NOT NULL REFERENCES public.users(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'declined')),
    note TEXT NOT NULL,
    source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.community_editions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.submission_reviews ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.source_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'complete', 'cancelled')),
    total INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.source_job_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES public.source_jobs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'complete', 'failed', 'cancelled')),
    candidates_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(job_id, position)
);
CREATE INDEX IF NOT EXISTS idx_source_jobs_user ON public.source_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_job_items_job ON public.source_job_items(job_id, position);
ALTER TABLE public.source_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_job_items ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.create_book_submission(p_record JSONB, p_source_ids TEXT[])
RETURNS VOID LANGUAGE plpgsql SET search_path = public AS $$
DECLARE source_id TEXT;
BEGIN
    INSERT INTO book_submissions(id,user_id,title,author,note,links_json,files_json,status)
        VALUES(p_record->>'id',p_record->>'user_id',p_record->>'title',p_record->>'author',
               p_record->>'note',p_record->'links_json',p_record->'files_json','pending');
    FOREACH source_id IN ARRAY p_source_ids LOOP
        INSERT INTO saved_books(id,user_id,book_id)
            VALUES('saved_' || md5((p_record->>'user_id') || source_id),p_record->>'user_id',source_id)
            ON CONFLICT(user_id,book_id) DO NOTHING;
    END LOOP;
END $$;
REVOKE ALL ON FUNCTION public.create_book_submission(JSONB,TEXT[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_book_submission(JSONB,TEXT[]) TO service_role;

-- One review transaction publishes only the selected editions and records why.
CREATE OR REPLACE FUNCTION public.review_submission(
    p_submission_id TEXT, p_reviewer_id TEXT, p_review_id TEXT,
    p_decision TEXT, p_note TEXT, p_title TEXT, p_author TEXT, p_books JSONB
) RETURNS VOID LANGUAGE plpgsql SET search_path = public AS $$
DECLARE source JSONB;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id=p_reviewer_id AND role='admin') THEN
        RAISE EXCEPTION 'Reviewer access required';
    END IF;
    IF p_decision NOT IN ('approved','declined') OR length(trim(p_note))=0 THEN
        RAISE EXCEPTION 'A decision and review note are required';
    END IF;
    PERFORM 1 FROM book_submissions WHERE id=p_submission_id AND status='pending' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Submission is no longer pending'; END IF;
    IF p_decision='approved' AND jsonb_array_length(p_books)=0 THEN
        RAISE EXCEPTION 'Select a source to publish';
    END IF;
    IF p_decision='approved' THEN
        FOR source IN SELECT value FROM jsonb_array_elements(p_books) LOOP
            IF source->>'submission_id' IS DISTINCT FROM p_submission_id THEN
                RAISE EXCEPTION 'Source does not belong to submission';
            END IF;
            INSERT INTO community_editions(id,submission_id,book_json)
                VALUES(source->>'id',p_submission_id,source);
        END LOOP;
    END IF;
    UPDATE book_submissions SET status=p_decision,title=p_title,author=p_author WHERE id=p_submission_id;
    INSERT INTO submission_reviews(id,submission_id,reviewer_id,decision,note,source_ids_json)
        VALUES(p_review_id,p_submission_id,p_reviewer_id,p_decision,p_note,
               (SELECT coalesce(jsonb_agg(value->>'id'),'[]'::jsonb) FROM jsonb_array_elements(p_books)));
END $$;
REVOKE ALL ON FUNCTION public.review_submission(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.review_submission(TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB) TO service_role;

-- The service-role key is used only by the server. Browser clients never
-- receive database or storage credentials.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reading_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.highlights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reading_companion_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.book_submissions ENABLE ROW LEVEL SECURITY;

-- Private review uploads and profile media. The application accesses this
-- bucket only with its server-side service role.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'waleeds-library',
    'waleeds-library',
    false,
    25165824,
    ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;
