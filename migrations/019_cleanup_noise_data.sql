-- ============================================================================
-- 019_cleanup_noise_data.sql
-- Mark noise rows in `projects` as confidence='low'.
-- Noise = news headlines, PDF filenames, person names, meaningless strings.
-- Also marks matching candidate_events as review_status='rejected'.
-- ============================================================================

-- ============================================================================
-- Rule 1: project name longer than 80 characters (news headlines)
-- ============================================================================
UPDATE projects
SET confidence = 'low'
WHERE LENGTH(name) > 80
  AND (confidence IS NULL OR confidence != 'low');

-- ============================================================================
-- Rule 2: name or summary contains noise keywords
-- ============================================================================
UPDATE projects
SET confidence = 'low'
WHERE (
  name ILIKE '%quarterly%'
  OR name ILIKE '%annual report%'
  OR name ILIKE '%earnings%'
  OR name ILIKE '% CEO %' OR name ILIKE 'CEO %' OR name ILIKE '% CEO'
  OR name ILIKE '%appoints%'
  OR name ILIKE '%resigns%'
  OR name ILIKE '%dividend%'
  OR name ILIKE '%share buyback%'
  OR name ILIKE '%stock %' OR name ILIKE '% stock%'
  OR name ILIKE '%merge%'
  OR name ILIKE '%acquisition%'
  OR name ILIKE '%layoff%' OR name ILIKE '%lay off%'
  OR name ILIKE '%restructuring%'
  OR name ILIKE '%.pdf%'
  OR name ILIKE '%.xlsx%'
  OR name ILIKE '%.csv%'
  OR name ILIKE '%.zip%'
  OR summary ILIKE '%quarterly%'
  OR summary ILIKE '%annual report%'
  OR summary ILIKE '%earnings%'
  OR summary ILIKE '% CEO %'
  OR summary ILIKE '%appoints%'
  OR summary ILIKE '%resigns%'
  OR summary ILIKE '%dividend%'
  OR summary ILIKE '%share buyback%'
  OR summary ILIKE '%merge%'
  OR summary ILIKE '%acquisition%'
  OR summary ILIKE '%layoff%' OR summary ILIKE '%lay off%'
  OR summary ILIKE '%restructuring%'
)
  AND (confidence IS NULL OR confidence != 'low');

-- ============================================================================
-- Rule 3: name is purely numeric or a meaningless string
--   - all digits
--   - all lowercase letters only (like 'abalone')
--   - very short gibberish (<= 3 chars, no vowels)
-- ============================================================================
UPDATE projects
SET confidence = 'low'
WHERE (
  name ~ '^[0-9]+$'
  OR name ~ '^[a-z]+$'
  OR (LENGTH(name) <= 3 AND name ~ '^[A-Za-z0-9]+$' AND name !~ '[AEIOUaeiou]')
)
  AND (confidence IS NULL OR confidence != 'low');

-- ============================================================================
-- Rule 4: name is ALL UPPERCASE with only spaces (likely oil-field codes, mostly noise)
--   Must be >= 2 words, all caps, no lowercase letters anywhere.
--   Exclude names containing known real-project keywords.
-- ============================================================================
UPDATE projects
SET confidence = 'low'
WHERE name ~ '^[A-Z][A-Z0-9 ]+$'            -- all uppercase (with optional digits and spaces)
  AND name !~ '[a-z]'                        -- zero lowercase letters
  AND name ~ ' '                             -- contains at least one space (multi-word)
  AND LENGTH(name) > 15                      -- longer than a simple acronym
  AND name !~* '(FPSO|FLNG|LNG|FPU|FSRU|TLP|SPAR|SEMI|FSO|MODU|MOPU|OFFSHORE|PLATFORM|DEVELOPMENT|PROJECT|FIELD|BASIN|BLOCK|PHASE|PIPELINE|TERMINAL|REFINERY|PETROBRAS|SHELL|EXXON|CHEVRON|TOTAL|BP|EQUINOR|STATOIL|PETRONAS|SAUDI|ARAMCO|ADNOC|QATAR|ENERGY|OIL|GAS|DEEP|WATER|PRODUCTION)'
  AND (confidence IS NULL OR confidence != 'low');

-- ============================================================================
-- Rule 5: name matches person-name pattern (like "John Smith")
--   Two words, each capitalized, followed by lowercase, no numbers/symbols.
--   Exclude names containing project-related keywords.
-- ============================================================================
UPDATE projects
SET confidence = 'low'
WHERE name ~ '^[A-Z][a-z]{1,20} [A-Z][a-z]{1,20}$'  -- exactly two capitalized words
  AND name !~ '[0-9]'                                   -- no digits
  AND name !~* '(Field|Project|Basin|Block|Platform|FPSO|FLNG|LNG|FPU|FSRU|Offshore|Energy|Oil|Gas|Petroleum|Terminal|Pipeline|Phase|Module|Area|Zone|Port|Bay|River|Sea|Ocean|Island|Coast|Cape|Mount|Point|South|North|East|West|Development|Production|Processing|Exploration|Drilling)'
  AND (confidence IS NULL OR confidence != 'low');

-- ============================================================================
-- Step 6: Mark corresponding candidate_events as rejected
--   Find candidate_events whose project_name_raw matches a noise-flagged project name
--   or which independently match the same noise rules.
-- ============================================================================
UPDATE candidate_events
SET review_status = 'rejected',
    evidence_quote = COALESCE(evidence_quote, '') || E'\n[Auto-rejected: Noise data — migration 019]'
WHERE review_status IN ('pending', 'accepted', 'auto_accepted')
  AND (
    -- match by project name to projects we just flagged as low confidence
    project_name_raw IN (
      SELECT name FROM projects
      WHERE confidence = 'low'
        AND name IS NOT NULL
        AND name != ''
    )
    -- or match the same noise rules independently
    OR LENGTH(project_name_raw) > 80
    OR project_name_raw ~ '^[0-9]+$'
    OR project_name_raw ~ '^[a-z]+$'
    OR (
      project_name_raw ~ '^[A-Z][a-z]{1,20} [A-Z][a-z]{1,20}$'
      AND project_name_raw !~ '[0-9]'
      AND project_name_raw !~* '(Field|Project|Basin|Block|Platform|FPSO|FLNG|LNG|FPU|FSRU|Offshore|Energy|Oil|Gas|Petroleum|Terminal|Pipeline|Phase|Module|Area|Zone|Port|Bay|River|Sea|Ocean|Island|Coast|Cape|Mount|Point|South|North|East|West|Development|Production|Processing|Exploration|Drilling)'
    )
  );

-- ============================================================================
-- Verification: report counts
-- ============================================================================
DO $$
DECLARE
  v_total_projects INT;
  v_noise_projects INT;
  v_clean_projects INT;
  v_rule1_count INT;
  v_rule2_count INT;
  v_rule3_count INT;
  v_rule4_count INT;
  v_rule5_count INT;
  v_events_rejected INT;
BEGIN
  SELECT COUNT(*) INTO v_total_projects FROM projects;

  SELECT COUNT(*) INTO v_noise_projects
    FROM projects WHERE confidence = 'low';

  SELECT COUNT(*) INTO v_clean_projects
    FROM projects WHERE confidence IN ('high', 'medium') OR confidence IS NULL;

  -- Count per rule (approximate — a single row may match multiple rules)
  SELECT COUNT(*) INTO v_rule1_count
    FROM projects WHERE confidence = 'low' AND LENGTH(name) > 80;

  SELECT COUNT(*) INTO v_rule2_count
    FROM projects WHERE confidence = 'low'
      AND (name ILIKE '%quarterly%' OR name ILIKE '%annual report%' OR name ILIKE '%earnings%'
           OR name ILIKE '%CEO%' OR name ILIKE '%appoints%' OR name ILIKE '%resigns%'
           OR name ILIKE '%dividend%' OR name ILIKE '%share buyback%'
           OR name ILIKE '%stock%' OR name ILIKE '%merge%' OR name ILIKE '%acquisition%'
           OR name ILIKE '%layoff%' OR name ILIKE '%restructuring%'
           OR name ILIKE '%.pdf%' OR name ILIKE '%.xlsx%' OR name ILIKE '%.csv%' OR name ILIKE '%.zip%'
           OR summary ILIKE '%quarterly%' OR summary ILIKE '%annual report%'
           OR summary ILIKE '%earnings%' OR summary ILIKE '%CEO%'
           OR summary ILIKE '%appoints%' OR summary ILIKE '%resigns%'
           OR summary ILIKE '%dividend%' OR summary ILIKE '%share buyback%'
           OR summary ILIKE '%merge%' OR summary ILIKE '%acquisition%'
           OR summary ILIKE '%layoff%' OR summary ILIKE '%restructuring%');

  SELECT COUNT(*) INTO v_rule3_count
    FROM projects WHERE confidence = 'low'
      AND (name ~ '^[0-9]+$' OR name ~ '^[a-z]+$'
           OR (LENGTH(name) <= 3 AND name ~ '^[A-Za-z0-9]+$' AND name !~ '[AEIOUaeiou]'));

  SELECT COUNT(*) INTO v_rule4_count
    FROM projects WHERE confidence = 'low'
      AND name ~ '^[A-Z][A-Z0-9 ]+$'
      AND name !~ '[a-z]'
      AND name ~ ' '
      AND LENGTH(name) > 15;

  SELECT COUNT(*) INTO v_rule5_count
    FROM projects WHERE confidence = 'low'
      AND name ~ '^[A-Z][a-z]{1,20} [A-Z][a-z]{1,20}$'
      AND name !~ '[0-9]';

  SELECT COUNT(*) INTO v_events_rejected
    FROM candidate_events WHERE review_status = 'rejected'
      AND evidence_quote LIKE '%migration 019%';

  RAISE NOTICE '============================================';
  RAISE NOTICE '  Migration 019 — Noise Data Cleanup Summary';
  RAISE NOTICE '============================================';
  RAISE NOTICE 'Total projects:            %', v_total_projects;
  RAISE NOTICE 'Marked as noise (low):     %', v_noise_projects;
  RAISE NOTICE 'Clean (high/medium):       %', v_clean_projects;
  RAISE NOTICE '---';
  RAISE NOTICE 'By rule (may overlap):';
  RAISE NOTICE '  Rule 1 (len > 80):       %', v_rule1_count;
  RAISE NOTICE '  Rule 2 (keywords):       %', v_rule2_count;
  RAISE NOTICE '  Rule 3 (numeric/gibber): %', v_rule3_count;
  RAISE NOTICE '  Rule 4 (ALL CAPS):       %', v_rule4_count;
  RAISE NOTICE '  Rule 5 (person name):    %', v_rule5_count;
  RAISE NOTICE '---';
  RAISE NOTICE 'Candidate events rejected: %', v_events_rejected;
  RAISE NOTICE '============================================';
END $$;
