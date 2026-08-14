-- 023_add_maturity.sql
-- Add maturity label to projects.
--
--   'mature'     — 成熟商机: has technical params (water_depth_m OR
--                  oil_capacity_bpd) AND >=1 linked candidate_events.
--                  Computed by the frontend on the fly; this column only
--                  stores the explicit DB label.
--   'potential'  — 潜在项目 (待挖掘池): real project but missing one or
--                  more of the above. Marked by scripts/opportunity_maturity.py.
--
-- Filtering is done client-side (src/lib/project_maturity.ts) — no code
-- reads this column yet; it is the durable record of the classification.
-- Run in Supabase SQL Editor.

BEGIN;

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS maturity text;

COMMENT ON COLUMN public.projects.maturity IS
  'DB label for opportunity maturity: ''potential'' = in the mining pool (real FPSO project, missing tech params / timeline events). ''mature'' reserved. Frontend still computes maturity live; this column is the durable record.';

COMMIT;
