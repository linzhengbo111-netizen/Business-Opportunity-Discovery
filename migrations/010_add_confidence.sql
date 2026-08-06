-- 010_add_confidence.sql
-- Add confidence column to projects and candidate_events tables.
-- Auto-ingest pipeline: all data flows directly into projects with AI confidence labels.
--
-- Confidence values: 'high', 'medium', 'low' — default 'medium'.
-- Backfill existing records based on source_registry priority:
--   P0 → high, P1 → medium, P2 → low.

BEGIN;

-- 1. Add confidence column to projects table
ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS confidence text NOT NULL DEFAULT 'medium';

-- Add check constraint (skip if already exists)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'projects_confidence_check'
      AND conrelid = 'public.projects'::regclass
  ) THEN
    ALTER TABLE public.projects
      ADD CONSTRAINT projects_confidence_check
      CHECK (confidence IN ('high', 'medium', 'low'));
  END IF;
END $$;

-- 2. Add confidence column to candidate_events table
ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS confidence text NOT NULL DEFAULT 'medium';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'candidate_events_confidence_check'
      AND conrelid = 'public.candidate_events'::regclass
  ) THEN
    ALTER TABLE public.candidate_events
      ADD CONSTRAINT candidate_events_confidence_check
      CHECK (confidence IN ('high', 'medium', 'low'));
  END IF;
END $$;

-- 3. Backfill existing projects: set confidence based on source_registry priority
--    Match projects.source_name → source_registry.source_name (exact or alias).
UPDATE public.projects p
SET confidence = COALESCE(
  (SELECT
    CASE
      WHEN sr.priority = 'P0' THEN 'high'
      WHEN sr.priority = 'P1' THEN 'medium'
      WHEN sr.priority = 'P2' THEN 'low'
      ELSE 'medium'
    END
   FROM public.source_registry sr
   WHERE sr.source_name = p.source_name
      OR sr.source_name IN (
        -- alias mappings (mirrors crawler/crawl.py SOURCE_NAME_ALIASES)
        CASE WHEN p.source_name = 'NSTA Field Development Plans' THEN 'NSTA 开发计划'
             WHEN p.source_name = 'Guyana EPA Oil & Gas Documents' THEN 'Guyana EPA'
             WHEN p.source_name = 'Guyana Petroleum Management' THEN 'Guyana 石油管理计划'
             WHEN p.source_name = 'Petrobras Supplier Registration' THEN 'Petrobras 供应商注册'
             WHEN p.source_name = 'Equinor Supplier Information' THEN 'Equinor 供应商信息'
             WHEN p.source_name = 'Petrofac Supplier Network' THEN 'Petrofac 供应商网络'
             WHEN p.source_name = 'MODEC Supply Chain News' THEN 'MODEC Supply Chain'
             WHEN p.source_name = 'SBM Offshore Newsroom' THEN 'SBM Offshore Newsroom'
             WHEN p.source_name = 'Equinor Rosebank Public Notices' THEN 'Equinor Rosebank 公告'
        END
      )
   LIMIT 1
  ),
  'medium'  -- fallback: no source_registry match → medium
);

-- 4. Backfill candidate_events: same logic
UPDATE public.candidate_events ce
SET confidence = COALESCE(
  (SELECT
    CASE
      WHEN sr.priority = 'P0' THEN 'high'
      WHEN sr.priority = 'P1' THEN 'medium'
      WHEN sr.priority = 'P2' THEN 'low'
      ELSE 'medium'
    END
   FROM public.source_registry sr
   WHERE sr.source_name = ce.source_name
      OR sr.source_name IN (
        CASE WHEN ce.source_name = 'NSTA Field Development Plans' THEN 'NSTA 开发计划'
             WHEN ce.source_name = 'Guyana EPA Oil & Gas Documents' THEN 'Guyana EPA'
             WHEN ce.source_name = 'Guyana Petroleum Management' THEN 'Guyana 石油管理计划'
             WHEN ce.source_name = 'Petrobras Supplier Registration' THEN 'Petrobras 供应商注册'
             WHEN ce.source_name = 'Equinor Supplier Information' THEN 'Equinor 供应商信息'
             WHEN ce.source_name = 'Petrofac Supplier Network' THEN 'Petrofac 供应商网络'
             WHEN ce.source_name = 'MODEC Supply Chain News' THEN 'MODEC Supply Chain'
             WHEN ce.source_name = 'SBM Offshore Newsroom' THEN 'SBM Offshore Newsroom'
             WHEN ce.source_name = 'Equinor Rosebank Public Notices' THEN 'Equinor Rosebank 公告'
        END
      )
   LIMIT 1
  ),
  'medium'
);

COMMIT;
