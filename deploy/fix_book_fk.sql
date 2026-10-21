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

