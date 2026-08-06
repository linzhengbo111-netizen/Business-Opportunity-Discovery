-- 011_add_procurement.sql
-- Add procurement_chain column to projects and candidate_events tables.
-- Stores comma-separated list of identified FPSO procurement entities
-- (contractors/shipyards, topsides EPC firms, equipment suppliers).
-- FPSO-only scope; nullable text, no constraints needed.

BEGIN;

-- 1. Add procurement_chain column to projects table
ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS procurement_chain text;

-- 2. Add procurement_chain column to candidate_events table
ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS procurement_chain text;

COMMIT;
