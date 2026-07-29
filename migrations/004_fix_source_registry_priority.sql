-- Fix source_registry tier/priority to match 《FPSO项目可用信息源使用手册》V1.0.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- 8 mismatches found during 2026-07-29 system audit:
--   MODEC Supply Chain:        P2→P0 (Tier 3, 手册P0)
--   Petrobras 供应商注册:       P1→P0, Tier 3→4 (手册P0/Tier4)
--   Guyana 石油管理计划:        P1→P0 (Tier 2, 手册P0)
--   World Oil:                 P0→P2 (Tier 1, 手册P2)
--   Offshore Energy:           P0→P1 (Tier 1, 手册P1)
--   Splash247:                 P1→P2 (Tier 1, 手册P2)
--   Petrofac 供应商网络:        P2→P1, Tier 3→4 (手册P1/Tier4)
--   Equinor 供应商信息:         Tier 3→4 (手册Tier4)

BEGIN;

-- 1. MODEC Supply Chain: P2 → P0 (manual says P0 for supply chain)
UPDATE public.source_registry
   SET priority = 'P0', notes = 'MODEC EPC contractor supply chain page. P0 per manual — directly affects procurement chain for Brazil FPSO projects.'
 WHERE source_name = 'MODEC Supply Chain';

-- 2. Petrobras 供应商注册: P1 → P0, Tier 3 → 4 (manual says P0/Tier4)
UPDATE public.source_registry
   SET priority = 'P0', tier = 4, notes = 'Petrobras supplier registration portal. P0/Tier4 per manual — 商业入口, directly affects procurement chain.'
 WHERE source_name = 'Petrobras 供应商注册';

-- 3. Guyana 石油管理计划: P1 → P0 (manual says P0/Tier2)
UPDATE public.source_registry
   SET priority = 'P0', notes = 'Guyana Ministry of Natural Resources. P0/Tier2 per manual — 官方验证 (licensing rounds, FPSO approvals).'
 WHERE source_name = 'Guyana 石油管理计划';

-- 4. World Oil: P0 → P2 (manual says P2/Tier1 — media should not be P0)
UPDATE public.source_registry
   SET priority = 'P2', notes = 'World Oil magazine. P2/Tier1 per manual — 线索发现, media source (not authoritative for verification).'
 WHERE source_name = 'World Oil';

-- 5. Offshore Energy: P0 → P1 (manual says P1/Tier1)
UPDATE public.source_registry
   SET priority = 'P1', notes = 'Offshore Energy news. P1/Tier1 per manual — 线索发现, broad offshore sector coverage.'
 WHERE source_name = 'Offshore Energy';

-- 6. Splash247: P1 → P2 (manual says P2/Tier1)
UPDATE public.source_registry
   SET priority = 'P2', notes = 'Splash247 maritime news. P2/Tier1 per manual — 线索发现, shipping-angle project scoops.'
 WHERE source_name = 'Splash247';

-- 7. Petrofac 供应商网络: P2 → P1, Tier 3 → 4 (manual says P1/Tier4)
UPDATE public.source_registry
   SET priority = 'P1', tier = 4, notes = 'Petrofac EPC supplier network. P1/Tier4 per manual — 商业入口, registration and opportunities for North Sea FPSO work.'
 WHERE source_name = 'Petrofac 供应商网络';

-- 8. Equinor 供应商信息: Tier 3 → 4 (manual says Tier4 for supplier portals)
UPDATE public.source_registry
   SET priority = 'P1', tier = 4, notes = 'Equinor supplier portal. P1/Tier4 per manual — 商业入口, qualification requirements and procurement pipeline.'
 WHERE source_name = 'Equinor 供应商信息';

-- Verify the changes
SELECT source_name, tier, priority, country_focus
  FROM public.source_registry
 ORDER BY priority, tier, source_name;

COMMIT;
