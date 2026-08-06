-- ============================================================================
-- 014_add_stainless_steel_to_candidate_events
-- ============================================================================
--
-- Adds stainless_steel and application columns to candidate_events table,
-- populated by PDF text extraction from ANP development plan adapters.
--
--   stainless_steel — comma-separated material keywords found in PDF text
--                     (e.g. "316L, Duplex 2205, Super Duplex 2507")
--   application     — application context where material is referenced
--                     (e.g. "Cargo Oil Tanks", "Process Piping")
-- ============================================================================

BEGIN;

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS stainless_steel text;

COMMENT ON COLUMN public.candidate_events.stainless_steel IS
  'Comma-separated stainless steel grade keywords extracted from source PDF text. e.g. "316L, Duplex 2205, Super Duplex 2507". Null when no material keywords found.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS application text;

COMMENT ON COLUMN public.candidate_events.application IS
  'Application context for the material reference (e.g. "Cargo Oil Tanks", "Process Piping"). Extracted from source PDF text. Null when not available.';

COMMIT;
