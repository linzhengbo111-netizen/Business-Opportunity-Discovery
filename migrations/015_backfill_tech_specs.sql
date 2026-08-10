-- ============================================================================
-- 015_backfill_tech_specs — 回填 ANP 项目技术规格字段
-- ============================================================================
--
-- 问题: promote_accepted_candidates() 在提升 candidate_events → projects 时
--       未传递 7 个技术规格字段 (water_depth_m, oil_capacity_bpd,
--       gas_capacity_mmcmd, hull_type, field_name, operator_name, basin),
--       以及 stainless_steel / application / procurement_chain,
--       导致已入库的 ANP 项目（44条）缺失这些字段。
--
-- 修复: 从 candidate_events 表中读取对应数据，回填到 projects 表。
--       匹配策略优先 candidate_events.project_name_raw 与 projects.name
--       的模糊匹配，仅处理 source_name LIKE 'ANP%' 的候选数据。
--
-- 安全: 仅 UPDATE 值为 NULL 的字段（不覆盖已有数据）。
--       所有操作用 DO $$ 块包裹，支持 dry-run 模式。
-- ============================================================================

BEGIN;

-- --------------------------------------------------------------------------
-- Step 1: 构建匹配桥梁 — 为每个 ANP 项目找最佳 candidate_events 行
-- --------------------------------------------------------------------------
-- 匹配优先级:
--   1. candidate_events.project_name_raw ILIKE projects.name (双向包含)
--   2. 必须是 ANP 来源 (source_name LIKE 'ANP%')
--   3. 候选行至少有一个技术规格字段非空
--   4. 每个 project 取技术字段最丰富的那条候选行
-- --------------------------------------------------------------------------

WITH anp_projects AS (
    -- 找出所有 ANP 来源且至少缺失一个技术字段的项目
    SELECT
        p.id AS project_id,
        p.name AS project_name,
        p.source_name,
        p.water_depth_m IS NULL     AS miss_water_depth,
        p.oil_capacity_bpd IS NULL  AS miss_oil_cap,
        p.gas_capacity_mmcmd IS NULL AS miss_gas_cap,
        p.hull_type IS NULL         AS miss_hull,
        p.field_name IS NULL        AS miss_field,
        p.operator_name IS NULL     AS miss_operator,
        p.basin IS NULL             AS miss_basin,
        p.stainless_steel IS NULL   AS miss_ss,
        p.application IS NULL       AS miss_app,
        p.procurement_chain IS NULL AS miss_proc
    FROM public.projects p
    WHERE p.source_name LIKE 'ANP%'
      AND (
          p.water_depth_m IS NULL
          OR p.oil_capacity_bpd IS NULL
          OR p.gas_capacity_mmcmd IS NULL
          OR p.hull_type IS NULL
          OR p.field_name IS NULL
          OR p.operator_name IS NULL
          OR p.basin IS NULL
          OR p.stainless_steel IS NULL
          OR p.application IS NULL
          OR p.procurement_chain IS NULL
      )
),
candidate_matches AS (
    -- 为每个 ANP 项目找到候选匹配行
    SELECT
        ap.project_id,
        ap.project_name,
        ce.id AS candidate_id,
        ce.project_name_raw,
        ce.water_depth_m,
        ce.oil_capacity_bpd,
        ce.gas_capacity_mmcmd,
        ce.hull_type,
        ce.field_name,
        ce.operator_name,
        ce.basin,
        ce.stainless_steel,
        ce.application,
        ce.procurement_chain,
        -- 计算该候选行的"数据丰富度"（非空技术字段计数）
        (CASE WHEN ce.water_depth_m      IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN ce.oil_capacity_bpd   IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN ce.gas_capacity_mmcmd IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN ce.hull_type          IS NOT NULL AND ce.hull_type != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.field_name         IS NOT NULL AND ce.field_name != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.operator_name      IS NOT NULL AND ce.operator_name != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.basin              IS NOT NULL AND ce.basin != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.stainless_steel    IS NOT NULL AND ce.stainless_steel != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.application        IS NOT NULL AND ce.application != '' THEN 1 ELSE 0 END +
         CASE WHEN ce.procurement_chain  IS NOT NULL AND ce.procurement_chain != '' THEN 1 ELSE 0 END
        ) AS richness,
        -- 最近日期优先
        COALESCE(ce.publication_date, ce.fetched_at::text) AS best_date
    FROM anp_projects ap
    JOIN public.candidate_events ce
      ON ce.source_name LIKE 'ANP%'
     AND (
         -- 双向模糊匹配
         ce.project_name_raw ILIKE '%' || ap.project_name || '%'
         OR ap.project_name ILIKE '%' || ce.project_name_raw || '%'
         -- 去掉 "FPSO " 前缀后再匹配
         OR ce.project_name_raw ILIKE '%' || REPLACE(ap.project_name, 'FPSO ', '') || '%'
         OR REPLACE(ap.project_name, 'FPSO ', '') ILIKE '%' || ce.project_name_raw || '%'
     )
     AND (
         -- 候选至少有一个有价值的技术字段
         ce.water_depth_m IS NOT NULL
         OR ce.oil_capacity_bpd IS NOT NULL
         OR ce.gas_capacity_mmcmd IS NOT NULL
         OR (ce.hull_type IS NOT NULL AND ce.hull_type != '')
         OR (ce.field_name IS NOT NULL AND ce.field_name != '')
         OR (ce.operator_name IS NOT NULL AND ce.operator_name != '')
         OR (ce.basin IS NOT NULL AND ce.basin != '')
         OR (ce.stainless_steel IS NOT NULL AND ce.stainless_steel != '')
         OR (ce.application IS NOT NULL AND ce.application != '')
         OR (ce.procurement_chain IS NOT NULL AND ce.procurement_chain != '')
     )
),
ranked_matches AS (
    -- 每个 project 取数据最丰富、日期最新的候选行
    SELECT DISTINCT ON (project_id)
        project_id,
        project_name,
        candidate_id,
        project_name_raw,
        water_depth_m,
        oil_capacity_bpd,
        gas_capacity_mmcmd,
        hull_type,
        field_name,
        operator_name,
        basin,
        stainless_steel,
        application,
        procurement_chain,
        richness
    FROM candidate_matches
    ORDER BY project_id, richness DESC, best_date DESC
)

-- --------------------------------------------------------------------------
-- Step 2: 预览待回填数据 (dry-run / 审计查询)
-- --------------------------------------------------------------------------
-- 取消下面 SELECT 的注释可预览匹配结果而不实际更新:
-- SELECT
--     rm.project_name,
--     rm.project_name_raw AS matched_candidate,
--     rm.richness AS field_count,
--     rm.water_depth_m,
--     rm.oil_capacity_bpd,
--     rm.gas_capacity_mmcmd,
--     rm.hull_type,
--     rm.field_name,
--     rm.operator_name,
--     rm.basin,
--     rm.stainless_steel,
--     rm.application,
--     rm.procurement_chain
-- FROM ranked_matches rm
-- ORDER BY rm.project_name;

-- --------------------------------------------------------------------------
-- Step 3: 执行回填 UPDATE
-- --------------------------------------------------------------------------
-- 每条更新只覆盖 NULL 字段，不覆盖已有数据（COALESCE 语义）
UPDATE public.projects p
SET
    water_depth_m      = COALESCE(p.water_depth_m,      rm.water_depth_m),
    oil_capacity_bpd   = COALESCE(p.oil_capacity_bpd,   rm.oil_capacity_bpd),
    gas_capacity_mmcmd = COALESCE(p.gas_capacity_mmcmd, rm.gas_capacity_mmcmd),
    hull_type          = COALESCE(NULLIF(p.hull_type, ''), NULLIF(rm.hull_type, '')),
    field_name         = COALESCE(NULLIF(p.field_name, ''), NULLIF(rm.field_name, '')),
    operator_name      = COALESCE(NULLIF(p.operator_name, ''), NULLIF(rm.operator_name, '')),
    basin              = COALESCE(NULLIF(p.basin, ''), NULLIF(rm.basin, '')),
    stainless_steel    = COALESCE(NULLIF(p.stainless_steel, ''), NULLIF(rm.stainless_steel, '')),
    application        = COALESCE(NULLIF(p.application, ''), NULLIF(rm.application, '')),
    procurement_chain  = COALESCE(NULLIF(p.procurement_chain, ''), NULLIF(rm.procurement_chain, ''))
FROM ranked_matches rm
WHERE p.id = rm.project_id
  AND (
      -- 仅当候选行确实有新数据可写时才执行 UPDATE
      (p.water_depth_m IS NULL AND rm.water_depth_m IS NOT NULL)
      OR (p.oil_capacity_bpd IS NULL AND rm.oil_capacity_bpd IS NOT NULL)
      OR (p.gas_capacity_mmcmd IS NULL AND rm.gas_capacity_mmcmd IS NOT NULL)
      OR ((p.hull_type IS NULL OR p.hull_type = '') AND rm.hull_type IS NOT NULL AND rm.hull_type != '')
      OR ((p.field_name IS NULL OR p.field_name = '') AND rm.field_name IS NOT NULL AND rm.field_name != '')
      OR ((p.operator_name IS NULL OR p.operator_name = '') AND rm.operator_name IS NOT NULL AND rm.operator_name != '')
      OR ((p.basin IS NULL OR p.basin = '') AND rm.basin IS NOT NULL AND rm.basin != '')
      OR ((p.stainless_steel IS NULL OR p.stainless_steel = '') AND rm.stainless_steel IS NOT NULL AND rm.stainless_steel != '')
      OR ((p.application IS NULL OR p.application = '') AND rm.application IS NOT NULL AND rm.application != '')
      OR ((p.procurement_chain IS NULL OR p.procurement_chain = '') AND rm.procurement_chain IS NOT NULL AND rm.procurement_chain != '')
  );

COMMIT;

-- ============================================================================
-- 验证查询（迁移后手动执行）:
-- ============================================================================
-- 随机查一条已回填的 ANP 项目，确认技术字段不再为空:
--
--   SELECT name, water_depth_m, oil_capacity_bpd, gas_capacity_mmcmd,
--          hull_type, field_name, operator_name, basin,
--          stainless_steel, application, procurement_chain
--   FROM public.projects
--   WHERE source_name LIKE 'ANP%'
--     AND water_depth_m IS NOT NULL
--   ORDER BY RANDOM()
--   LIMIT 1;
-- ============================================================================
