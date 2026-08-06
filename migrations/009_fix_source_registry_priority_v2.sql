-- Fix source_registry tier/priority to match 《FPSO项目可用信息源使用手册》V1.0 (2026-07-22).
-- Run this in Supabase Dashboard → SQL Editor.
--
-- 7 mismatches found during 2026-08-06 system audit (AUDIT_REPORT_2026-08-06.md):
--   MODEC Supply Chain:        P2→P0 (Tier 3, 手册P0)
--   World Oil:                 P0→P2 (Tier 1, 手册P2)
--   Splash247:                 P1→P2 (Tier 1, 手册P2)
--   Guyana 石油管理计划:        P1→P0 (Tier 2, 手册P0)
--   Petrobras 供应商注册:       P1→P0, Tier 3→4 (手册P0/Tier4)
--   Offshore Energy:           P0→P1 (Tier 1, 手册P1)
--   Petrofac 供应商网络:        P2→P1, Tier 3→4 (手册P1/Tier4)
--
-- Idempotent — safe to run multiple times.

BEGIN;

-- 1. MODEC Supply Chain: P2 → P0 (保持 Tier 3)
UPDATE public.source_registry
   SET priority = 'P0',
       notes = 'MODEC EPC contractor supply chain page. P0/Tier3 per manual — directly affects procurement chain for Brazil FPSO projects.'
 WHERE source_name = 'MODEC Supply Chain';

-- 2. World Oil: P0 → P2 (保持 Tier 1)
UPDATE public.source_registry
   SET priority = 'P2',
       notes = 'World Oil magazine. P2/Tier1 per manual — 线索发现, media source (not authoritative for verification).'
 WHERE source_name = 'World Oil';

-- 3. Splash247: P1 → P2 (保持 Tier 1)
UPDATE public.source_registry
   SET priority = 'P2',
       notes = 'Splash247 maritime news. P2/Tier1 per manual — 线索发现, shipping-angle project scoops.'
 WHERE source_name = 'Splash247';

-- 4. Guyana 石油管理计划: P1 → P0 (保持 Tier 2)
UPDATE public.source_registry
   SET priority = 'P0',
       notes = 'Guyana Ministry of Natural Resources. P0/Tier2 per manual — 官方验证 (licensing rounds, FPSO approvals).'
 WHERE source_name = 'Guyana 石油管理计划';

-- 5. Petrobras 供应商注册: P1 → P0, Tier 3 → 4
UPDATE public.source_registry
   SET priority = 'P0', tier = 4,
       notes = 'Petrobras supplier registration portal. P0/Tier4 per manual — 商业入口, directly affects procurement chain.'
 WHERE source_name = 'Petrobras 供应商注册';

-- 6. Offshore Energy: P0 → P1 (保持 Tier 1)
UPDATE public.source_registry
   SET priority = 'P1',
       notes = 'Offshore Energy news. P1/Tier1 per manual — 线索发现, broad offshore sector coverage.'
 WHERE source_name = 'Offshore Energy';

-- 7. Petrofac 供应商网络: P2 → P1, Tier 3 → 4
UPDATE public.source_registry
   SET priority = 'P1', tier = 4,
       notes = 'Petrofac EPC supplier network. P1/Tier4 per manual — 商业入口, registration and opportunities for North Sea FPSO work.'
 WHERE source_name = 'Petrofac 供应商网络';

-- Verify the changes
SELECT source_name, tier, priority, country_focus
  FROM public.source_registry
 ORDER BY priority, tier, source_name;

COMMIT;
