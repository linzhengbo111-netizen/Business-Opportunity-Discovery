-- 025_replace_status_with_phase.sql
--
-- Replace the 4-value status taxonomy (Under Construction / Planned /
-- Delivered / Unknown) with 9 standardized lifecycle phases:
--   Concept / Planning / Design / Approval / EPC Award / Procurement /
--   Construction / Commissioning / Delivery
--
-- Steps:
--   1. Back up the old data (rollback path: projects_status_backup).
--   2. Rename projects.status → projects.phase (text, nullable).
--   3. Map existing values:
--        Delivered          → 'Delivery'
--        Under Construction → 'Construction' (default)
--                             'Procurement' when description mentions procurement
--        Planned            → 'Planning' (default)
--                             'Approval' when description mentions EIA / 环评
--                             'Design'   when description mentions FEED
--        Unknown            → NULL (待 AI 判断)
--   4. Add candidate_events.phase (text, nullable) — populated by the
--      --backfill-phases AI backfill / ai_event_extractor.
--
-- Run in Supabase SQL Editor. Frontend reads `phase` with a legacy
-- `status` fallback (src/lib/project_phase.ts), so old caches keep working.

BEGIN;

-- ---- 1. Backup ----
DROP TABLE IF EXISTS public.projects_status_backup;
CREATE TABLE public.projects_status_backup AS
SELECT id, name, status, summary, created_at
FROM public.projects;

COMMENT ON TABLE public.projects_status_backup IS
  'Backup of projects.status before migration 025 (status → phase). Rollback: UPDATE projects SET status = b.status FROM projects_status_backup b WHERE projects.id = b.id; then ALTER TABLE projects RENAME COLUMN phase TO status.';

-- ---- 2. Rename ----
ALTER TABLE IF EXISTS public.projects
  RENAME COLUMN status TO phase;

ALTER TABLE public.projects
  ALTER COLUMN phase DROP NOT NULL;

COMMENT ON COLUMN public.projects.phase IS
  'Lifecycle phase: Concept / Planning / Design / Approval / EPC Award / Procurement / Construction / Commissioning / Delivery. NULL = unknown (pending AI judgment). Replaces the legacy status column (migration 025).';

-- ---- 3. Data mapping ----
UPDATE public.projects
SET phase = CASE
  WHEN phase = 'Delivered' THEN 'Delivery'
  WHEN phase = 'Under Construction'
       AND (summary ~* 'procurement|purchase|tender|procuração') THEN 'Procurement'
  WHEN phase = 'Under Construction' THEN 'Construction'
  WHEN phase = 'Planned'
       AND (summary ~* '\bEIA\b|environmental|环评') THEN 'Approval'
  WHEN phase = 'Planned'
       AND (summary ~* '\bFEED\b|front-end engineering') THEN 'Design'
  WHEN phase = 'Planned' THEN 'Planning'
  WHEN phase = 'Unknown' THEN NULL
  ELSE phase
END
WHERE phase IN
  ('Delivered', 'Under Construction', 'Planned', 'Unknown', '', NULL);

-- ---- 4. candidate_events phase column ----
ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS phase text;

COMMENT ON COLUMN public.candidate_events.phase IS
  'Lifecycle phase at the time of this event (same taxonomy as projects.phase). NULL = not judged yet.';

COMMIT;
