-- ============================================================================
-- 016_downgrade_historical_projects.sql
-- Downgrade confidence for Delivered and pre-2023 projects.
-- These projects are noise for stainless-steel business opportunity discovery
-- (projects already finished or in production before our window of interest).
-- ============================================================================

-- Step 1: Downgrade confidence for Delivered projects (regardless of date).
-- Delivered = project already built and operating — no procurement opportunity.
UPDATE projects
SET confidence = 'low'
WHERE status = 'Delivered'
  AND (confidence IS NULL OR confidence != 'low');

-- Step 2: Downgrade confidence for projects with source_date before 2023.
-- Historical projects from 2010-2022 — not useful for current opportunity mining.
UPDATE projects
SET confidence = 'low'
WHERE source_date < '2023-01-01'
  AND source_date != ''
  AND (confidence IS NULL OR confidence != 'low');

-- Step 3: Mark candidate_events with publication_date before 2023 as rejected.
-- These events are auto-rejected by the updated auto_classify Rule E.
-- This step cleans up any existing data ingested before the rule was added.
UPDATE candidate_events
SET review_status = 'rejected',
    evidence_quote = COALESCE(evidence_quote, '') || E'\n[Auto-rejected: Historical data (pre-2023) — migration 016]'
WHERE review_status IN ('pending', 'accepted', 'auto_accepted')
  AND publication_date < '2023-01-01'
  AND publication_date != '';

-- Step 4 (optional): Report affected counts for verification.
DO $$
DECLARE
  v_delivered_low INT;
  v_old_low INT;
  v_events_rejected INT;
BEGIN
  SELECT COUNT(*) INTO v_delivered_low
    FROM projects WHERE status = 'Delivered' AND confidence = 'low';
  SELECT COUNT(*) INTO v_old_low
    FROM projects WHERE source_date < '2023-01-01' AND source_date != '' AND confidence = 'low';
  SELECT COUNT(*) INTO v_events_rejected
    FROM candidate_events WHERE review_status = 'rejected'
      AND evidence_quote LIKE '%migration 016%';

  RAISE NOTICE '--- Migration 016 Summary ---';
  RAISE NOTICE 'Delivered projects downgraded: %', v_delivered_low;
  RAISE NOTICE 'Pre-2023 projects downgraded: %', v_old_low;
  RAISE NOTICE 'Candidate events rejected:   %', v_events_rejected;
END $$;
