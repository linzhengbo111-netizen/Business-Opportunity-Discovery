-- 022_dedup_candidate_events.sql
-- ================================
-- Remove duplicate candidate_events rows where (project_name_raw, event_type, summary)
-- are identical. Keep only the earliest row per group (lowest id).
--
-- Run before: 4963 total, 1650 duplicate groups, 2759 excess rows.
-- Run after:  ~2204 unique rows remaining.

DELETE FROM candidate_events
WHERE id NOT IN (
    SELECT min_id
    FROM (
        SELECT MIN(id) AS min_id
        FROM candidate_events
        GROUP BY project_name_raw, event_type, summary
    ) AS keepers
);

-- Verify with:
-- SELECT project_name_raw, event_type, summary, COUNT(*) AS cnt
-- FROM candidate_events
-- GROUP BY project_name_raw, event_type, summary
-- HAVING COUNT(*) > 1;
