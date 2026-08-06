-- ============================================================================
-- 012_fix_encoding — diagnose and fix double-encoded UTF-8 text
-- ============================================================================
--
-- Root cause: when a server omits charset in Content-Type, Python `requests`
-- may default to ISO-8859-1. This decodes actual UTF-8 bytes as Latin-1
-- characters, producing mojibake like "PETRÃ" instead of "PETRÓ".
--
-- Fix approach: convert the string through Latin-1 back to UTF-8.
-- Only apply to rows that show mojibake signatures (Ã/Â + continuation byte)
-- and don't contain CJK characters (which can't survive Latin-1 round-trip).
--
-- Run the diagnostic queries first. Then apply fixes selectively.
-- ============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Step 1: Diagnostic — find potentially garbled rows
-- --------------------------------------------------------------------------

-- Pattern: Ã (U+00C3) or Â (U+00C2) followed by a UTF-8 continuation byte
-- This is the signature of double-encoded UTF-8 → Latin-1 text.

-- Check projects table
SELECT id, name,
       summary AS garbled_summary,
       convert_from(convert_to(summary, 'LATIN1'), 'UTF8') AS fixed_summary
FROM projects
WHERE summary ~ '[ÃÂÂ][\x80-\xbf]'
  AND summary !~ '[一-鿿぀-ゟ゠-ヿ]'  -- skip CJK rows
LIMIT 20;

-- Check candidate_events table
SELECT id, project_name_raw,
       summary AS garbled_summary,
       convert_from(convert_to(summary, 'LATIN1'), 'UTF8') AS fixed_summary
FROM candidate_events
WHERE summary ~ '[ÃÂÂ][\x80-\xbf]'
  AND summary !~ '[一-鿿぀-ゟ゠-ヿ]'
LIMIT 20;

-- Also check evidence_quote, raw_json fields
SELECT id, project_name_raw,
       evidence_quote AS garbled,
       convert_from(convert_to(evidence_quote, 'LATIN1'), 'UTF8') AS fixed
FROM candidate_events
WHERE evidence_quote ~ '[ÃÂÂ][\x80-\xbf]'
  AND evidence_quote !~ '[一-鿿぀-ゟ゠-ヿ]'
LIMIT 20;

-- --------------------------------------------------------------------------
-- Step 2: Safe fix function (creates no side effects until update runs)
-- --------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fix_double_encoded_utf8(t text) RETURNS text AS $$
BEGIN
    -- Only attempt fix on text that survives Latin-1 round-trip
    -- (text with characters outside Latin-1 range will fail convert_to)
    BEGIN
        RETURN convert_from(convert_to(t, 'LATIN1'), 'UTF8');
    EXCEPTION WHEN OTHERS THEN
        RETURN t;  -- can't fix, return as-is
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- --------------------------------------------------------------------------
-- Step 3: Apply fix (review diagnostic results first, then uncomment)
-- --------------------------------------------------------------------------

-- Fix projects.summary:
-- UPDATE projects
-- SET summary = fix_double_encoded_utf8(summary)
-- WHERE summary ~ '[ÃÂÂ][\x80-\xbf]'
--   AND summary !~ '[一-鿿぀-ゟ゠-ヿ]';

-- Fix candidate_events.summary:
-- UPDATE candidate_events
-- SET summary = fix_double_encoded_utf8(summary)
-- WHERE summary ~ '[ÃÂÂ][\x80-\xbf]'
--   AND summary !~ '[一-鿿぀-ゟ゠-ヿ]';

-- Fix candidate_events.evidence_quote:
-- UPDATE candidate_events
-- SET evidence_quote = fix_double_encoded_utf8(evidence_quote)
-- WHERE evidence_quote ~ '[ÃÂÂ][\x80-\xbf]'
--   AND evidence_quote !~ '[一-鿿぀-ゟ゠-ヿ]';

-- Fix candidate_events.project_name_raw (less likely to be garbled, but check):
-- UPDATE candidate_events
-- SET project_name_raw = fix_double_encoded_utf8(project_name_raw)
-- WHERE project_name_raw ~ '[ÃÂÂ][\x80-\xbf]'
--   AND project_name_raw !~ '[一-鿿぀-ゟ゠-ヿ]';

-- --------------------------------------------------------------------------
-- Step 4: Cleanup (optional — keep function if future fixes needed)
-- --------------------------------------------------------------------------

-- DROP FUNCTION IF EXISTS fix_double_encoded_utf8;

COMMIT;
