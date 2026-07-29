-- Create snapshot_registry table for ANP FPSO CSV adapter snapshot tracking.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- This table stores metadata for each CSV snapshot ingested by the ANP adapter.
-- Full snapshot records are stored in local JSON files (crawler/data/anp/*.json);
-- this table tracks the file path, hash, and record counts for auditability.
--
-- Also adds event_type column to candidate_events for regulatory data classification.

-- 1. Create snapshot_registry table
CREATE TABLE IF NOT EXISTS public.snapshot_registry (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name     text NOT NULL,
    source_url      text,
    snapshot_date   text NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    file_path       text,
    file_hash_sha256 text,
    record_count    int NOT NULL DEFAULT 0,
    source_type     text NOT NULL DEFAULT 'GOVERNMENT',
    tier            int NOT NULL DEFAULT 2,
    priority        text NOT NULL DEFAULT 'P0',
    country_focus   text NOT NULL DEFAULT 'Brazil',
    access_method   text NOT NULL DEFAULT 'CSV',
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- 2. Add index for fast lookup of latest snapshot per source
CREATE INDEX IF NOT EXISTS idx_snapshot_registry_source_date
    ON public.snapshot_registry (source_name, snapshot_date DESC);

-- 3. Enable RLS
ALTER TABLE IF EXISTS public.snapshot_registry ENABLE ROW LEVEL SECURITY;

-- 4. Permissive policy for anon key
DO $$
BEGIN
    EXECUTE COALESCE(
        (SELECT string_agg('DROP POLICY IF EXISTS "' || policyname || '" ON public.snapshot_registry;', E'\n')
         FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'snapshot_registry'),
        'SELECT 1'
    );
END $$;

CREATE POLICY "Allow all for anon key on snapshot_registry"
  ON public.snapshot_registry
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- 5. Add event_type and raw_json columns to candidate_events if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'event_type'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN event_type text DEFAULT 'NEWS_ARTICLE';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'raw_json'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN raw_json text;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'previous_raw_json'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN previous_raw_json text;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'change_type'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN change_type text;
    END IF;
END $$;
