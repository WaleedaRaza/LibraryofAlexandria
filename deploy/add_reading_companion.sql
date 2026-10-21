-- Release 25: private, citation-backed conversation over a reader's saved memory.
-- Apply in the existing Alexandra Supabase project before deploying this image.

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

ALTER TABLE public.reading_companion_messages ENABLE ROW LEVEL SECURITY;
