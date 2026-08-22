-- ============================================================================
-- 026_fix_delivery_confidence.sql
-- Fix delivery project pollution: re-apply the migration 016 downgrade on the
-- CURRENT schema (phase column, post-025) and clean up rows that later
-- auto_ingest runs overwrote back to 'high'.
--
-- Root cause:
--   016 downgraded `status = 'Delivered'`; 025 renamed the column to `phase`.
--   Subsequent auto_ingest runs with P0 sources set confidence='high' again
--   with no phase guard (fixed in crawler/crawl.py auto_ingest_to_projects).
-- ============================================================================

-- Step 1: Downgrade all delivered/commissioning projects regardless of source.
-- Delivered/commissioning = vessel built or finishing — no procurement
-- opportunity for stainless-steel business.
UPDATE projects
SET confidence = 'low'
WHERE phase IN ('Delivery', 'Commissioning')
  AND (confidence IS NULL OR confidence != 'low');

-- Step 2: Report verification counts.
DO $$
DECLARE
  v_terminal_total INT;
  v_terminal_high INT;
  v_high_total INT;
BEGIN
  SELECT COUNT(*) INTO v_terminal_total
    FROM projects WHERE phase IN ('Delivery', 'Commissioning');
  SELECT COUNT(*) INTO v_terminal_high
    FROM projects WHERE phase IN ('Delivery', 'Commissioning')
      AND confidence = 'high';
  SELECT COUNT(*) INTO v_high_total
    FROM projects WHERE confidence = 'high';

  RAISE NOTICE '--- Migration 026 Summary ---';
  RAISE NOTICE 'Delivery/Commissioning projects:      %', v_terminal_total;
  RAISE NOTICE '  of which still high confidence:     %', v_terminal_high;
  RAISE NOTICE 'All high-confidence projects:         %', v_high_total;
  RAISE NOTICE 'High-confidence share in terminal:    %', v_terminal_high;
END $$;
