-- Add canonical_project_id column to candidate_events table.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- Per 《FPSO项目可用信息源使用手册》: candidate_events must include
-- canonical_project_id (归一化后项目ID), nullable — filled after normalization.
--
-- Also adds publication_date column if not already present.

-- 1. Add canonical_project_id column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'canonical_project_id'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN canonical_project_id text;
    END IF;
END $$;

-- 2. Add evidence_quote column if not already present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'evidence_quote'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN evidence_quote text;
    END IF;
END $$;

-- 3. Add publication_date column if not already present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'candidate_events'
          AND column_name = 'publication_date'
    ) THEN
        ALTER TABLE public.candidate_events
        ADD COLUMN publication_date text;
    END IF;
END $$;

-- Verify columns
SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name = 'candidate_events'
 ORDER BY ordinal_position;
