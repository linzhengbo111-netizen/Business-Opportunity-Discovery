-- Create source_registry table per FPSO项目可用信息源使用手册.
-- Run this in Supabase Dashboard → SQL Editor.
--
-- The table catalogs all information sources used for FPSO project discovery,
-- organized by tier (1=线索发现, 2=官方验证, 3=采购链拆解, 4=商业入口),
-- priority (P0/P1/P2), country focus, and access method.

-- 1. Create table (skip if exists)
CREATE TABLE IF NOT EXISTS public.source_registry (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name     text NOT NULL,
    source_url      text,
    source_type     text NOT NULL CHECK (source_type IN ('GOVERNMENT', 'OPERATOR', 'CONTRACTOR', 'MEDIA', 'SUPPLIER_PORTAL')),
    tier            int  NOT NULL CHECK (tier BETWEEN 1 AND 4),
    priority        text NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    country_focus   text NOT NULL,
    access_method   text NOT NULL CHECK (access_method IN ('CSV', 'HTML', 'PDF', 'API')),
    crawl_frequency text NOT NULL CHECK (crawl_frequency IN ('daily', 'weekly', 'monthly')),
    is_active       boolean NOT NULL DEFAULT true,
    last_crawled_at timestamptz,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- 2. Enable RLS
ALTER TABLE IF EXISTS public.source_registry ENABLE ROW LEVEL SECURITY;

-- 3. Drop existing policies if any (no-op when table has no policies yet)
DO $$
BEGIN
    EXECUTE COALESCE(
        (SELECT string_agg('DROP POLICY IF EXISTS "' || policyname || '" ON public.source_registry;', E'\n')
         FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'source_registry'),
        'SELECT 1'  -- no policies exist yet, skip
    );
END $$;

-- 4. Create permissive policy for anon key
CREATE POLICY "Allow all for anon key on source_registry"
  ON public.source_registry
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- 5. Seed initial data (16 sources across Brazil, Guyana, UK, and global media)
INSERT INTO public.source_registry (source_name, source_url, source_type, tier, priority, country_focus, access_method, crawl_frequency, notes)
VALUES
  -- ========== Brazil (4) ==========
  ('ANP FPSO CSV',
   'https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos',
   'GOVERNMENT', 2, 'P0', 'Brazil', 'CSV', 'daily',
   'ANP open data portal. Direct CSV download with FPSO production volumes by field.'),

  ('ANP 开发计划',
   'https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/dados-de-producao',
   'GOVERNMENT', 2, 'P0', 'Brazil', 'HTML', 'weekly',
   'ANP development plan listing. Approved field development plans including FPSO projects.'),

  ('Petrobras 供应商注册',
   'https://canalfornecedor.petrobras.com.br/',
   'SUPPLIER_PORTAL', 3, 'P1', 'Brazil', 'HTML', 'weekly',
   'Petrobras supplier registration portal. Procurement notices and tender lists for FPSO topside equipment.'),

  ('MODEC Supply Chain',
   'https://www.modec.com/supply-chain/',
   'CONTRACTOR', 3, 'P2', 'Brazil', 'HTML', 'weekly',
   'MODEC EPC contractor supply chain page. Sub-supplier opportunities for Brazil FPSO projects.'),

  -- ========== Guyana (4) ==========
  ('Guyana EPA',
   'https://www.epaguyana.org/',
   'GOVERNMENT', 2, 'P0', 'Guyana', 'HTML', 'weekly',
   'Guyana Environmental Protection Agency. Environmental permits and EIAs for offshore FPSO development.'),

  ('Guyana 石油管理计划',
   'https://petroleum.gov.gy/',
   'GOVERNMENT', 2, 'P1', 'Guyana', 'HTML', 'weekly',
   'Guyana Ministry of Natural Resources. Petroleum management plans, licensing rounds, and FPSO approvals.'),

  ('ExxonMobil Guyana 环境页面',
   'https://corporate.exxonmobil.com/locations/guyana',
   'OPERATOR', 2, 'P1', 'Guyana', 'HTML', 'weekly',
   'ExxonMobil Guyana operations page. Stabroek block FPSO environmental data and project updates.'),

  ('SBM Offshore Newsroom',
   'https://www.sbmoffshore.com/newsroom/',
   'CONTRACTOR', 3, 'P1', 'Guyana', 'HTML', 'daily',
   'SBM Offshore press releases. FPSO delivery, contract awards, and fleet updates for Guyana operations.'),

  -- ========== UK (4) ==========
  ('NSTA 开发计划',
   'https://www.nstauthority.co.uk/',
   'GOVERNMENT', 2, 'P0', 'UK', 'HTML', 'weekly',
   'North Sea Transition Authority. UKCS field development plans, FPSO consent decisions, and environmental statements.'),

  ('Equinor Rosebank 公告',
   'https://www.equinor.com/energy/rosebank',
   'OPERATOR', 2, 'P0', 'UK', 'HTML', 'daily',
   'Equinor Rosebank project page. Official announcements, FID updates, and FPSO contract awards for North Sea.'),

  ('Equinor 供应商信息',
   'https://www.equinor.com/supply',
   'SUPPLIER_PORTAL', 3, 'P1', 'UK', 'HTML', 'weekly',
   'Equinor supplier portal. Qualification requirements, upcoming tenders, and procurement pipeline for UKCS projects.'),

  ('Petrofac 供应商网络',
   'https://www.petrofac.com/supply-chain/',
   'CONTRACTOR', 3, 'P2', 'UK', 'HTML', 'weekly',
   'Petrofac EPC supplier network. Registration and opportunities for North Sea FPSO brownfield/modification work.'),

  -- ========== Global Media (4) ==========
  ('Offshore Energy',
   'https://www.offshore-energy.biz/',
   'MEDIA', 1, 'P0', 'Global', 'HTML', 'daily',
   'Offshore Energy news. Broad offshore sector coverage: FPSO contract awards, project FIDs, and fleet movements.'),

  ('OE Digital',
   'https://www.oedigital.com/',
   'MEDIA', 1, 'P1', 'Global', 'HTML', 'daily',
   'OE Digital (Offshore Engineer). Deepwater and FPSO technical articles, project timelines, and EPC updates.'),

  ('World Oil',
   'https://www.worldoil.com/',
   'MEDIA', 1, 'P0', 'Global', 'HTML', 'daily',
   'World Oil magazine. Upstream project announcements, FPSO discoveries, and regional development roundups.'),

  ('Splash247',
   'https://splash247.com/',
   'MEDIA', 1, 'P1', 'Global', 'HTML', 'daily',
   'Splash247 maritime news. Offshore vessel/FPSO logistics, fleet reports, and shipping-angle project scoops.');
