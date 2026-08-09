-- Migration 018: Add corrosive_media column for H2S/CO2/sour service tracking
-- Supports stainless steel material recommendation engine with corrosion data.
-- Run: psql <connection-string> -f migrations/018_add_corrosive_media.sql

-- Add JSONB column to candidate_events (crawler writes here first)
ALTER TABLE candidate_events
  ADD COLUMN IF NOT EXISTS corrosive_media JSONB;

-- Add JSONB column to projects (synced during auto-ingest)
ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS corrosive_media JSONB;

-- Comment on columns for schema documentation
COMMENT ON COLUMN candidate_events.corrosive_media IS
  'Corrosive media parameters extracted from article text. JSON schema: {h2s: bool, co2: bool, sour_service: bool, chloride: bool, details: string}';

COMMENT ON COLUMN projects.corrosive_media IS
  'Corrosive media parameters merged from candidate_events. JSON schema: {h2s: bool, co2: bool, sour_service: bool, chloride: bool, details: string}';
