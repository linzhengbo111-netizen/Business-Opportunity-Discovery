-- 008_add_industry_field.sql
-- Add industry column to projects table.
-- Used by the frontend for FPSO detection (material_matcher.ts checks
-- project.industry === "FPSO") and by the dashboard industry filter.
-- Nullable text; backfill for existing FPSO rows is done separately
-- (hull_type or name-based).

BEGIN;

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS industry text;

COMMENT ON COLUMN public.projects.industry IS
  'Industry vertical, e.g. FPSO. Backfilled from hull_type/name for FPSO rows.';

COMMIT;
