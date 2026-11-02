-- Name Ten: daily taste game, profile shelves and badges.
-- Apply in the Supabase SQL editor before deploying an image with NAME_TEN_ENABLED=true.
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS public.ten_game (
    id INTEGER PRIMARY KEY,                 -- shown as "No. 47"; 0 = free play
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'free')),
    prompt TEXT NOT NULL,
    opens_on DATE UNIQUE,                   -- null for free play
    created_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO public.ten_game (id, kind, prompt) VALUES (0, 'free', 'Your ten, no rules.')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.ten_play (
    id TEXT PRIMARY KEY,                    -- play_<hex>
    game_id INTEGER NOT NULL REFERENCES public.ten_game(id),
    user_id TEXT REFERENCES public.users(id) ON DELETE CASCADE,
    anon_id TEXT,                           -- signed cookie until signup, then claimed
    combo_hash TEXT NOT NULL,               -- sha256 of the sorted work keys
    raw_score DOUBLE PRECISION NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    max_overlap INTEGER NOT NULL,
    findings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    verdict_json JSONB,                     -- null until the judge returns
    badges_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    share_slug TEXT UNIQUE,                 -- set only when the player posts it
    created_at TIMESTAMPTZ DEFAULT now(),
    CHECK (user_id IS NOT NULL OR anon_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ten_one_daily_play
    ON public.ten_play (game_id, user_id) WHERE game_id <> 0 AND user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ten_play_rank ON public.ten_play (game_id, raw_score);
CREATE INDEX IF NOT EXISTS idx_ten_play_anon ON public.ten_play (anon_id) WHERE anon_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.ten_play_item (
    play_id TEXT NOT NULL REFERENCES public.ten_play(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 10),
    work_key TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    book_id TEXT,                           -- catalog work id when the book is in the library
    status TEXT NOT NULL CHECK (status IN ('library', 'finder', 'unverified')),
    PRIMARY KEY (play_id, position)
);
CREATE INDEX IF NOT EXISTS idx_ten_item_work ON public.ten_play_item (work_key, play_id);

CREATE TABLE IF NOT EXISTS public.ten_work_stat (
    work_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    list_count INTEGER NOT NULL DEFAULT 0,
    prior_popularity DOUBLE PRECISION      -- Open Library reading-log count, cached
);

CREATE TABLE IF NOT EXISTS public.ten_pair_stat (
    work_a TEXT NOT NULL,
    work_b TEXT NOT NULL,
    list_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (work_a, work_b),
    CHECK (work_a < work_b)
);

CREATE TABLE IF NOT EXISTS public.shelf_item (
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 10),
    work_key TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    book_id TEXT,
    proof_state TEXT NOT NULL DEFAULT 'declared'
        CHECK (proof_state IN ('declared', 'sampled', 'read', 'argued')),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, position)
);

CREATE TABLE IF NOT EXISTS public.user_badge (
    user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    badge_key TEXT NOT NULL,
    play_id TEXT REFERENCES public.ten_play(id) ON DELETE SET NULL,
    earned_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, badge_key, earned_at)
);

-- Counters for the 45 pairs of a list, read in one call.
CREATE OR REPLACE FUNCTION public.ten_pair_counts(keys TEXT[])
RETURNS TABLE (work_a TEXT, work_b TEXT, list_count INTEGER)
LANGUAGE sql STABLE AS $$
    SELECT p.work_a, p.work_b, p.list_count FROM public.ten_pair_stat p
    WHERE p.work_a = ANY(keys) AND p.work_b = ANY(keys);
$$;

-- The earlier play sharing the most books with this list.
CREATE OR REPLACE FUNCTION public.ten_closest_play(keys TEXT[])
RETURNS TABLE (play_id TEXT, shared INTEGER)
LANGUAGE sql STABLE AS $$
    SELECT i.play_id, count(*)::INTEGER AS shared FROM public.ten_play_item i
    WHERE i.work_key = ANY(keys)
    GROUP BY i.play_id ORDER BY shared DESC, i.play_id LIMIT 1;
$$;

-- Pairs that link this list to books outside it, strongest first (for the missing eleventh).
CREATE OR REPLACE FUNCTION public.ten_co_named(keys TEXT[], lim INTEGER DEFAULT 400)
RETURNS TABLE (work_a TEXT, work_b TEXT, list_count INTEGER)
LANGUAGE sql STABLE AS $$
    SELECT p.work_a, p.work_b, p.list_count FROM public.ten_pair_stat p
    WHERE (p.work_a = ANY(keys)) <> (p.work_b = ANY(keys))
    ORDER BY p.list_count DESC LIMIT lim;
$$;

-- One call per play: bump 10 work counters and 45 pair counters.
CREATE OR REPLACE FUNCTION public.ten_record_list(keys TEXT[], titles TEXT[], authors TEXT[])
RETURNS void LANGUAGE sql AS $$
    INSERT INTO public.ten_work_stat (work_key, title, author, list_count)
    SELECT k, t, a, 1 FROM unnest(keys, titles, authors) AS u(k, t, a)
    ON CONFLICT (work_key) DO UPDATE SET list_count = public.ten_work_stat.list_count + 1;
    INSERT INTO public.ten_pair_stat (work_a, work_b, list_count)
    SELECT x, y, 1 FROM unnest(keys) x, unnest(keys) y WHERE x < y
    ON CONFLICT (work_a, work_b) DO UPDATE SET list_count = public.ten_pair_stat.list_count + 1;
$$;

ALTER TABLE public.ten_game ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ten_play ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ten_play_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ten_work_stat ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ten_pair_stat ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shelf_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_badge ENABLE ROW LEVEL SECURITY;
