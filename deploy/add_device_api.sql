-- Release 26: pairing codes for reading devices (the Kindle plugin).
-- Apply in the Supabase SQL editor before deploying this image.

CREATE TABLE IF NOT EXISTS public.device_codes (
    code TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL,
    device_name TEXT NOT NULL,
    user_id TEXT REFERENCES public.users(id) ON DELETE CASCADE,
    claimed_token TEXT,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL
);
ALTER TABLE public.device_codes ENABLE ROW LEVEL SECURITY;
