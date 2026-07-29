-- Fix candidate_events table RLS policies.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- Data flow: Crawler → candidate_events → Manual Review → --promote → projects
--
-- The candidate_events table already exists with columns:
--   id, project_name_raw, country, summary, source_name, source_url,
--   review_status, created_at

-- Ensure RLS allows all operations with anon key
ALTER TABLE IF EXISTS public.candidate_events ENABLE ROW LEVEL SECURITY;

-- Drop existing restrictive policies if any, then re-create permissive one
DO $$
BEGIN
    EXECUTE (
        SELECT string_agg('DROP POLICY IF EXISTS "' || policyname || '" ON public.candidate_events;', E'\n')
        FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'candidate_events'
    );
END $$;

CREATE POLICY "Allow all for anon key"
  ON public.candidate_events
  FOR ALL
  USING (true)
  WITH CHECK (true);
