-- 020: Add opportunity_score JSONB column to projects table
-- Stores the S5 Opportunity Scoring Engine result:
--   {totalScore, grade, dimensions: {procurement, factoryMatch, reachability, value, confidence}, summary, recommendedAction}
ALTER TABLE projects ADD COLUMN IF NOT EXISTS opportunity_score JSONB;

COMMENT ON COLUMN projects.opportunity_score IS 'Opportunity scoring result: {totalScore, grade, dimensions: {...}, summary, recommendedAction}';
