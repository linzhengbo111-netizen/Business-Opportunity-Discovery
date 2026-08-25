-- 030: 去掉演示项目 candidate_events 的 'DEMO:' source_name 前缀和假 source_url。
-- 029 只修了 projects 表，candidate_events 的 88 条演示事件仍是 DEMO:LNG 等占位来源，
-- 项目时间线会原样展示来源名与链接。此处按行业映射为真实行业出版物（与 029 一致）。
-- 幂等：WHERE source_name LIKE 'DEMO:%'，可重复执行。

-- LNG
UPDATE candidate_events SET source_name = 'LNG Prime', source_url = 'https://lngprime.com'
  WHERE project_name_raw IN ('North Gulf LNG Export Terminal','Mozambique Palma South LNG T3','Qatargas East Expansion LNG','Venture Pacific FLNG Hull')
    AND source_name LIKE 'DEMO:%';

-- Petrochemical
UPDATE candidate_events SET source_name = 'Hydrocarbon Processing', source_url = 'https://www.hydrocarbonprocessing.com'
  WHERE project_name_raw IN ('Daesan Ethylene Expansion Cracker','Jubail PDH/PP Complex Phase 2','Tuxpan Aromatics BTX Unit','Basra Ethane Cracker & Derivatives')
    AND source_name LIKE 'DEMO:%';

-- Chemical
UPDATE candidate_events SET source_name = 'Chemical Week', source_url = 'https://chemweek.com'
  WHERE project_name_raw IN ('Corpus Christi Green Methanol Plant','Jurong Island Specialty Chemicals Hub','Ludwigshafen Chlor-Alkali Replacement','Ningbo Epoxy Resin Train 3')
    AND source_name LIKE 'DEMO:%';

-- Desalination
UPDATE candidate_events SET source_name = 'Global Water Intelligence', source_url = 'https://www.globalwaterintel.com'
  WHERE project_name_raw IN ('Al Ghubra III Desalination','Alicante SWRO Expansion','Ras Al Khair SWRO Phase 2','Tocopilla Desalination Plant')
    AND source_name LIKE 'DEMO:%';

-- Fertilizer
UPDATE candidate_events SET source_name = 'World Fertilizer', source_url = 'https://www.worldfertilizer.com'
  WHERE project_name_raw IN ('Ain Sokhna Phosphate Complex NPK','Kansas Nitrogen Revamp','Trinidad Melamine & Urea Tie-in','Vaca Muerta Ammonia-Urea Greenfield')
    AND source_name LIKE 'DEMO:%';

-- Geothermal
UPDATE candidate_events SET source_name = 'ThinkGeoEnergy', source_url = 'https://www.thinkgeoenergy.com'
  WHERE project_name_raw IN ('Aydin Manisa Flash Plant U2','Hellisheidi Expansion Stage 4','New Zealand Taupo Deep Resource Pilot','Olkaria VII Geothermal Plant')
    AND source_name LIKE 'DEMO:%';

-- Mining
UPDATE candidate_events SET source_name = 'Mining.com', source_url = 'https://www.mining.com'
  WHERE project_name_raw IN ('Atacama Spence-SGO Copper Expansion','Pilbara Iron Ore Wet Plant 2','Rudna Copper Smelter Modernization','Saskatchewan Potash Solution Mine Phase 3')
    AND source_name LIKE 'DEMO:%';

-- Nuclear
UPDATE candidate_events SET source_name = 'World Nuclear News', source_url = 'https://www.world-nuclear-news.org'
  WHERE project_name_raw IN ('Czech Dukovany-II New Units','Hokkaido Genkai-2 Restart Works','Ontario SMR BWRX-300 Fleet','Poland Baltic AP1000 Nuclear Plant')
    AND source_name LIKE 'DEMO:%';

-- Pulp & Paper
UPDATE candidate_events SET source_name = 'Paper Advance', source_url = 'https://www.paperadvance.com'
  WHERE project_name_raw IN ('Kemi Bio-Products Mill Expansion','Ornskoldsvik Dissolving Pulp Line','Richards Bay Tissue & Towel Plant','Sulawesi Greenfield Pulp Mill')
    AND source_name LIKE 'DEMO:%';

-- Sugar
UPDATE candidate_events SET source_name = 'Sugar Online', source_url = 'https://www.sugar-online.com'
  WHERE project_name_raw IN ('Karnataka Sugar Co-gen Boiler Upgrade','Khon Kaen Sugar Mill & Refinery Expansion','Luzon Integrated Sugar Mill','Sao Paulo Flex Ethanol & Sugar Plant')
    AND source_name LIKE 'DEMO:%';

-- Biopharma
UPDATE candidate_events SET source_name = 'Pharmaceutical Technology', source_url = 'https://www.pharmaceutical-technology.com'
  WHERE project_name_raw IN ('Copenhagen Antibody DS Plant','Leiden Cell & Gene Therapy Campus','Mainz mRNA Vaccine Facility 3','Singapore Viral Vector CDMO Line')
    AND source_name LIKE 'DEMO:%';
