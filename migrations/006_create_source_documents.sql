-- Create source_documents table for tracking downloaded raw files.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- Per 《FPSO项目可用信息源使用手册》: the data flow requires
--   source_registry → source_documents → candidate_events → projects
-- This table fills the missing source_documents layer.
--
-- Each row represents one raw file (HTML, CSV, PDF, XLSX) downloaded
-- from a registered source. The file_hash_sha256 enables deduplication
-- and audit trail verification.

-- 1. Create table
CREATE TABLE IF NOT EXISTS public.source_documents (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         bigint REFERENCES public.source_registry(id) ON DELETE SET NULL,
    file_name         text NOT NULL,
    file_path         text,
    file_hash_sha256  text NOT NULL,
    file_type         text NOT NULL CHECK (file_type IN ('CSV', 'HTML', 'PDF', 'XLSX', 'ZIP', 'JSON', 'OTHER')),
    file_size_bytes   bigint,
    publication_date  text,
    fetched_at        timestamptz NOT NULL DEFAULT now(),
    original_url      text,
    download_url      text,
    snapshot_json     jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_source_documents_source_id
    ON public.source_documents (source_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_file_hash
    ON public.source_documents (file_hash_sha256);

CREATE INDEX IF NOT EXISTS idx_source_documents_fetched_at
    ON public.source_documents (fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_documents_file_type
    ON public.source_documents (file_type);

-- 3. Enable RLS
ALTER TABLE IF EXISTS public.source_documents ENABLE ROW LEVEL SECURITY;

-- 4. Permissive policy for anon key
DO $$
BEGIN
    EXECUTE COALESCE(
        (SELECT string_agg('DROP POLICY IF EXISTS "' || policyname || '" ON public.source_documents;', E'\n')
         FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'source_documents'),
        'SELECT 1'
    );
END $$;

CREATE POLICY "Allow all for anon key on source_documents"
  ON public.source_documents
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- 5. Verification query
-- Run this after adapters have populated data:
--
-- SELECT
--     sr.source_name,
--     sr.priority,
--     sr.tier,
--     COUNT(sd.id) AS doc_count,
--     MIN(sd.fetched_at) AS first_fetched,
--     MAX(sd.fetched_at) AS last_fetched,
--     SUM(sd.file_size_bytes) AS total_bytes
-- FROM public.source_registry sr
-- LEFT JOIN public.source_documents sd ON sd.source_id = sr.id
-- GROUP BY sr.id, sr.source_name, sr.priority, sr.tier
-- ORDER BY sr.priority, sr.tier, doc_count DESC;
