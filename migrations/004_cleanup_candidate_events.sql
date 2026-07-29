-- Cleanup stale candidate_events data.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- Problem: 6 old workflow runs accumulated large volumes of pending data
-- that were auto-promoted without manual review. Low-quality entries
-- (ARTICLE_MENTION with no real FPSO project match) now pollute the
-- projects table via auto-promote.
--
-- This script provides:
--   1. Diagnostic queries to assess data quality
--   2. Archive old pending entries that pre-date auto-promote
--   3. Find likely-duplicate projects for manual review

-- =========================================================================
-- 1. DIAGNOSTIC: count by review_status
-- =========================================================================
SELECT review_status, count(*) AS cnt
FROM public.candidate_events
GROUP BY review_status
ORDER BY cnt DESC;

-- =========================================================================
-- 2. DIAGNOSTIC: find projects likely to be duplicates (same display name,
--    merged via normalizeProjectName in --promote)
-- =========================================================================
SELECT name, count(*) AS occurrences
FROM public.projects
GROUP BY name
HAVING count(*) > 1
ORDER BY occurrences DESC;

-- =========================================================================
-- 3. DIAGNOSTIC: find projects with very short summaries (likely junk)
-- =========================================================================
SELECT id, name, country, status, length(summary) AS summary_len, source_name
FROM public.projects
WHERE length(summary) < 30
ORDER BY summary_len ASC
LIMIT 50;

-- =========================================================================
-- 4. DIAGNOSTIC: count candidate_events by event_type
-- =========================================================================
SELECT event_type, count(*) AS cnt
FROM public.candidate_events
GROUP BY event_type
ORDER BY cnt DESC;

-- =========================================================================
-- 5. CLEANUP: archive pending entries older than 14 days
--    (these pre-date the --auto-promote workflow and have already been
--     promoted; keeping them as 'pending' is misleading)
-- =========================================================================
UPDATE public.candidate_events
SET review_status = 'archived'
WHERE review_status = 'pending'
  AND fetched_at < now() - INTERVAL '14 days';

-- =========================================================================
-- 6. CLEANUP: archive all remaining pending entries if you're confident
--    --auto-promote has already processed everything useful.
--    UNCOMMENT to run:
-- =========================================================================
-- UPDATE public.candidate_events
-- SET review_status = 'archived'
-- WHERE review_status = 'pending';

-- =========================================================================
-- 7. OPTIONAL: delete pure ARTICLE_MENTION entries that were never promoted
--    and have no canonical_project_id (i.e., normalizeProjectName failed).
--    These are news mentions with no identifiable FPSO project.
--    UNCOMMENT to run:
-- =========================================================================
-- DELETE FROM public.candidate_events
-- WHERE review_status = 'archived'
--   AND event_type = 'ARTICLE_MENTION'
--   AND canonical_project_id IS NULL;

-- =========================================================================
-- POST-CLEANUP: re-run diagnostics to verify
-- =========================================================================
SELECT review_status, count(*) AS cnt
FROM public.candidate_events
GROUP BY review_status
ORDER BY cnt DESC;
