-- ============================================================================
-- 013_add_technical_specs — FPSO技术规格字段与不锈钢选型推荐
-- ============================================================================
--
-- 为 projects 和 candidate_events 表新增技术规格字段:
--   water_depth_m      — 水深（米）
--   oil_capacity_bpd   — 石油产能（桶/天）
--   gas_capacity_mmcmd — 天然气产能（百万立方米/天）
--   hull_type          — 船体类型（Spread Moored, Turret, FLNG conversion 等）
--   field_name         — 所属油气田
--   operator_name      — 运营商
--   basin              — 盆地
--
-- projects 表额外新增:
--   recommendation_json — 不锈钢选型匹配结果（JSONB）
--
-- 所有字段可为空，不影响现有数据完整性。
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. projects 表 — 技术规格字段
-- ============================================================================

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS water_depth_m int;

COMMENT ON COLUMN public.projects.water_depth_m IS
  'Water depth in meters. Extracted from regulatory CSV or article text. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS oil_capacity_bpd int;

COMMENT ON COLUMN public.projects.oil_capacity_bpd IS
  'Oil production capacity in barrels per day (bpd). Extracted from regulatory CSV or article text. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS gas_capacity_mmcmd int;

COMMENT ON COLUMN public.projects.gas_capacity_mmcmd IS
  'Gas production capacity in million cubic meters per day (MMcmd). Extracted from regulatory CSV or article text. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS hull_type text;

COMMENT ON COLUMN public.projects.hull_type IS
  'FPSO hull type: Spread Moored, Turret, FLNG conversion, etc. Extracted from article text or regulatory data. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS field_name text;

COMMENT ON COLUMN public.projects.field_name IS
  'Oil/gas field name the FPSO serves. Extracted from regulatory CSV (CAMPOS) or article text. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS operator_name text;

COMMENT ON COLUMN public.projects.operator_name IS
  'Operator company name. Extracted from regulatory CSV (OPERADOR) or article text. Null when unknown.';

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS basin text;

COMMENT ON COLUMN public.projects.basin IS
  'Sedimentary basin name. Extracted from regulatory CSV (BACIA) or article text. Null when unknown.';

-- ============================================================================
-- 2. projects 表 — 不锈钢选型推荐（JSONB）
-- ============================================================================

ALTER TABLE IF EXISTS public.projects
  ADD COLUMN IF NOT EXISTS recommendation_json jsonb;

COMMENT ON COLUMN public.projects.recommendation_json IS
  'Stainless steel material matching result. Structured JSON:
   {
     "grades": ["316L", "Duplex 2205", ...],
     "applications": ["Cargo Oil Tanks", "Process Piping", ...],
     "confidence": "high"|"medium"|"low",
     "reasoning": "Water depth >1500m → Super Duplex recommended for ..."
   }
   Null when no technical specs are available for matching.';

-- ============================================================================
-- 3. candidate_events 表 — 技术规格字段（不含推荐）
-- ============================================================================

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS water_depth_m int;

COMMENT ON COLUMN public.candidate_events.water_depth_m IS
  'Water depth in meters. Extracted from source data. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS oil_capacity_bpd int;

COMMENT ON COLUMN public.candidate_events.oil_capacity_bpd IS
  'Oil production capacity in barrels per day (bpd). Extracted from source data. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS gas_capacity_mmcmd int;

COMMENT ON COLUMN public.candidate_events.gas_capacity_mmcmd IS
  'Gas production capacity in million cubic meters per day (MMcmd). Extracted from source data. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS hull_type text;

COMMENT ON COLUMN public.candidate_events.hull_type IS
  'FPSO hull type if mentioned in source text. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS field_name text;

COMMENT ON COLUMN public.candidate_events.field_name IS
  'Oil/gas field name extracted from source data. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS operator_name text;

COMMENT ON COLUMN public.candidate_events.operator_name IS
  'Operator company name extracted from source data. Null when unknown.';

ALTER TABLE IF EXISTS public.candidate_events
  ADD COLUMN IF NOT EXISTS basin text;

COMMENT ON COLUMN public.candidate_events.basin IS
  'Sedimentary basin name extracted from source data. Null when unknown.';

-- ============================================================================
-- 4. 索引（可选 — 加速按油田/运营商/盆地筛选）
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_projects_field_name ON public.projects(field_name)
  WHERE field_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_projects_operator_name ON public.projects(operator_name)
  WHERE operator_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_projects_basin ON public.projects(basin)
  WHERE basin IS NOT NULL;

COMMIT;
