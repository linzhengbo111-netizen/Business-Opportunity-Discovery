-- ============================================================================
-- 028_seed_all_industries.sql
-- 行业扩展种子数据：11 个行业 × 4 个演示项目 + 每项目 2 条 candidate_events。
-- 幂等：所有 INSERT 均带 WHERE NOT EXISTS 守卫，可重复执行。
-- 同时回填 industry IS NULL 的历史行为 'FPSO'（与前端 normalizeIndustry 一致）。
-- 演示项目 source_name 统一标记 DEMO:<行业>，后续可用真实数据替换。
-- ============================================================================

BEGIN;

-- Step 0: 历史行回填 — 前端将 NULL 当 FPSO 处理，落库保持一致。
UPDATE public.projects SET industry = 'FPSO' WHERE industry IS NULL;

-- Step 1: 种子项目
-- LNG — North Gulf LNG Export Terminal
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'North Gulf LNG Export Terminal', 'USA', 'LNG', 'Approval', 'high', 'Operator: North Gulf LNG LLC | Capacity: 12.0 Mtpa | Trains: 2 | Refrigeration: Air Products C3-MR | Cold Box: Linde | Start: 2028 | Cryogenic stainless piping and duplex equipment for liquefaction trains',
    'DEMO:LNG' , 'https://demo.miaoda.local/north-gulf-lng-export-terminal', '2026-08-23',
    '304L, 316L, 9% Ni steel, Super Duplex 2507 (seawater)', 'Cryogenic piping, cold boxes, LNG storage inner tanks, seawater cooling', 'Bechtel, Chiyoda, Baker Hughes'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'North Gulf LNG Export Terminal');

-- LNG — Mozambique Palma South LNG T3
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Mozambique Palma South LNG T3', 'Mozambique', 'LNG', 'EPC Award', 'high', 'Operator: TotalEnergies led JV | Capacity: 4.5 Mtpa | Train: 1 | Feed gas: Coral Sul offshore | Start: 2029 | Corrosive offshore gas requires duplex piping in amine and dehydration units',
    'DEMO:LNG' , 'https://demo.miaoda.local/mozambique-palma-south-lng-t3', '2026-08-23',
    'Duplex 2205, 316L, Incoloy 825', 'Acid gas removal, dehydration, HP flare, seawater intake', 'Saipem, Technip Energies, Mitsubishi Heavy'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Mozambique Palma South LNG T3');

-- LNG — Qatargas East Expansion LNG
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Qatargas East Expansion LNG', 'Qatar', 'LNG', 'Procurement', 'medium', 'Operator: QatarEnergy | Capacity: 16.0 Mtpa | Trains: 2 | Refrigeration: AP-X hybrid | Start: 2030 | Expansion of the existing LNG complex with new utilities and cryogenic storage',
    'DEMO:LNG' , 'https://demo.miaoda.local/qatargas-east-expansion-lng', '2026-08-23',
    '304L, 9% Ni, Super Duplex 2507', 'LNG rundown lines, boil-off gas compressors, firewater piping', 'Technip Energies, Consolidated Contractors'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Qatargas East Expansion LNG');

-- LNG — Venture Pacific FLNG Hull
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Venture Pacific FLNG Hull', 'Australia', 'LNG', 'Planning', 'medium', 'Operator: Venture Pacific Energy | Capacity: 3.0 Mtpa FLNG | Hull: 320m barge | Start: 2031 | FEED study evaluating floating liquefaction for marginal Browse Basin fields',
    'DEMO:LNG' , 'https://demo.miaoda.local/venture-pacific-flng-hull', '2026-08-23',
    '316L, Duplex 2205, Inconel 625', 'FLNG topsides cryogenic piping, flare tower, seawater lift', 'MODEC, SBM Offshore, Samsung Heavy'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Venture Pacific FLNG Hull');

-- Petrochemical — Daesan Ethylene Expansion Cracker
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Daesan Ethylene Expansion Cracker', 'South Korea', 'Petrochemical', 'Construction', 'high', 'Operator: Lotte Chemical | Feed: naphtha | Ethylene: 1.0 Mtpa | Start: 2027 | New mixed-feed cracker with downstream PE/PP units; furnace tubes in HK40/HP alloys',
    'DEMO:Petrochemical' , 'https://demo.miaoda.local/daesan-ethylene-expansion-cracker', '2026-08-23',
    '304H, 321H, HK-40, HP modified, Incoloy 800H', 'Cracking furnace tubes, quench exchangers, acetylene converter, product rundown', 'Samsung Engineering, Tecnimont, Daelim'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Daesan Ethylene Expansion Cracker');

-- Petrochemical — Jubail PDH/PP Complex Phase 2
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Jubail PDH/PP Complex Phase 2', 'Saudi Arabia', 'Petrochemical', 'EPC Award', 'high', 'Operator: Gulf Polymers Co | Propane dehydrogenation 650 ktpa + PP 550 ktpa | Start: 2028 | High-temperature reactors and catalyst regeneration require heat-resistant stainless',
    'DEMO:Petrochemical' , 'https://demo.miaoda.local/jubail-pdh/pp-complex-phase-2', '2026-08-23',
    '304H, 321H, 347H, Duplex 2205', 'PDH reactor internals, regeneration loops, PP extrusion piping, cooling water', 'McDermott, Hanwha, Tecnimont'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Jubail PDH/PP Complex Phase 2');

-- Petrochemical — Tuxpan Aromatics BTX Unit
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Tuxpan Aromatics BTX Unit', 'Mexico', 'Petrochemical', 'Procurement', 'medium', 'Operator: Pemex JV | Capacity: paraxylene 800 ktpa | Feed: reformate | Start: 2028 | Aromatics complex revamp with new isomerization and CCR reformer units',
    'DEMO:Petrochemical' , 'https://demo.miaoda.local/tuxpan-aromatics-btx-unit', '2026-08-23',
    '316L, 321H, Duplex 2205, Incoloy 825', 'CCR reformer heater tubes, acid handling, benzene rundown lines', 'ICA Fluor, Samsung Engineering'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Tuxpan Aromatics BTX Unit');

-- Petrochemical — Basra Ethane Cracker & Derivatives
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Basra Ethane Cracker & Derivatives', 'Iraq', 'Petrochemical', 'Approval', 'medium', 'Operator: Basra Petrochem Co | Ethylene: 1.5 Mtpa | Feed: ethane from South Gas Co | Start: 2030 | Grassroots cracker with PE units to monetize associated gas',
    'DEMO:Petrochemical' , 'https://demo.miaoda.local/basra-ethane-cracker-&-derivatives', '2026-08-23',
    '304H, 321H, HP modified, 316L', 'Furnace coils, quench system, caustic wash, flare header', 'Petrofac, Tecnimont, Hyundai E&C'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Basra Ethane Cracker & Derivatives');

-- Chemical — Ludwigshafen Chlor-Alkali Replacement
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ludwigshafen Chlor-Alkali Replacement', 'Germany', 'Chemical', 'Construction', 'high', 'Operator: BASF | Chlorine: 600 ktpa membrane electrolysis | Start: 2027 | Replacement of mercury-cell plant with membrane technology; titanium and high-nickel alloys in electrolyzer loop',
    'DEMO:Chemical' , 'https://demo.miaoda.local/ludwigshafen-chlor-alkali-replacement', '2026-08-23',
    'Titanium Gr.1/2, 254 SMO, 316L, Alloy 59', 'Electrolyzer cells, brine circuit, hypochlorite lines, caustic storage', 'Thyssenkrupp Uhde, Bilfinger'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ludwigshafen Chlor-Alkali Replacement');

-- Chemical — Jurong Island Specialty Chemicals Hub
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Jurong Island Specialty Chemicals Hub', 'Singapore', 'Chemical', 'Procurement', 'high', 'Operator: SpecialtyChem Asia | Products: pharma intermediates, aroma chemicals | Start: 2027 | Multi-train specialty chemicals hub with high-alloy process piping for corrosive intermediates',
    'DEMO:Chemical' , 'https://demo.miaoda.local/jurong-island-specialty-chemicals-hub', '2026-08-23',
    '316L, 904L, 254 SMO, Hastelloy C-276', 'Reactor jacketing, solvent recovery, effluent treatment, clean utilities', 'Worley, Samsung C&T, Rotary Engineering'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Jurong Island Specialty Chemicals Hub');

-- Chemical — Ningbo Epoxy Resin Train 3
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ningbo Epoxy Resin Train 3', 'China', 'Chemical', 'EPC Award', 'medium', 'Operator: Ningbo Epoxy Co | Epoxy resin: 150 ktpa | Feed: ECH/BPA | Start: 2027 | Third production train with chlorine-related processes requiring corrosion-resistant equipment',
    'DEMO:Chemical' , 'https://demo.miaoda.local/ningbo-epoxy-resin-train-3', '2026-08-23',
    '316L, Duplex 2205, Titanium, Alloy 20', 'ECH reactors, caustic scrubbers, waste acid concentration', 'Sinopec Engineering, China Huanqiu'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ningbo Epoxy Resin Train 3');

-- Chemical — Corpus Christi Green Methanol Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Corpus Christi Green Methanol Plant', 'USA', 'Chemical', 'Planning', 'medium', 'Operator: Gulf Methanol Renewables | Methanol: 900 ktpa from green H2 + captured CO2 | Start: 2029 | First-of-kind e-methanol plant; electrolysis at 30 bar requires duplex and super-austenitic alloys',
    'DEMO:Chemical' , 'https://demo.miaoda.local/corpus-christi-green-methanol-plant', '2026-08-23',
    'Duplex 2205, 254 SMO, 316L', 'HP electrolysis, methanol synthesis loop, CO2 capture column internals', 'KBR, Technip Energies, Fluor'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Corpus Christi Green Methanol Plant');

-- Fertilizer — Vaca Muerta Ammonia-Urea Greenfield
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Vaca Muerta Ammonia-Urea Greenfield', 'Argentina', 'Fertilizer', 'EPC Award', 'high', 'Operator: YPF Agro JV | Ammonia: 1.2 Mtpa | Urea: 2.1 Mtpa | Feed: Vaca Muerta gas | Start: 2028 | Greenfield nitrogen complex with high-pressure synthesis loops in urea-grade alloys',
    'DEMO:Fertilizer' , 'https://demo.miaoda.local/vaca-muerta-ammonia-urea-greenfield', '2026-08-23',
    '316L Urea grade, 25Cr22Ni2Mo (Safurex), 304L, Duplex 2205', 'Urea synthesis loop, strippers, HP condensate, ammonium carbamate piping', 'Tecnimont, Petrofac, SACDE'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Vaca Muerta Ammonia-Urea Greenfield');

-- Fertilizer — Ain Sokhna Phosphate Complex NPK
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ain Sokhna Phosphate Complex NPK', 'Egypt', 'Fertilizer', 'Construction', 'high', 'Operator: Egyptian Fertilizer Co | NPK/DAP: 1.0 Mtpa | Feed: phosphate rock + sulfur | Start: 2027 | Phosphate complex with phosphoric acid and DAP granulation trains',
    'DEMO:Fertilizer' , 'https://demo.miaoda.local/ain-sokhna-phosphate-complex-npk', '2026-08-23',
    '904L, Alloy 20, 316L, Duplex 2205', 'Phosphoric acid evaporators, slurry piping, scrubbers, sulfuric acid dilution', 'Orascom Construction, Tecnimont, Wuhuan'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ain Sokhna Phosphate Complex NPK');

-- Fertilizer — Kansas Nitrogen Revamp
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Kansas Nitrogen Revamp', 'USA', 'Fertilizer', 'Procurement', 'medium', 'Operator: Mid-America Nitrogen | Ammonia: 700 ktpa revamp | Start: 2027 | Debottlenecking of primary reformer and CO2 removal with new alloy components',
    'DEMO:Fertilizer' , 'https://demo.miaoda.local/kansas-nitrogen-revamp', '2026-08-23',
    '321H, Incoloy 800H, 316L, Duplex 2205', 'Reformer tubes, waste heat boiler, CO2 absorber internals, letdown valves', 'KBR, Brown & Root, Zachry'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Kansas Nitrogen Revamp');

-- Fertilizer — Trinidad Melamine & Urea Tie-in
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Trinidad Melamine & Urea Tie-in', 'Trinidad and Tobago', 'Fertilizer', 'Planning', 'medium', 'Operator: Trinidad Nitrogen Holdings | Melamine: 80 ktpa tie-in to existing urea | Start: 2029 | Value-add melamine unit using urea feed; HP section in urea-grade stainless',
    'DEMO:Fertilizer' , 'https://demo.miaoda.local/trinidad-melamine-&-urea-tie-in', '2026-08-23',
    '316L Urea grade, 25Cr22Ni2Mo, 304L', 'Melamine reactor, off-gas scrubbing, urea tie-in piping', 'Saipem, Toyo Engineering, Massy Wood'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Trinidad Melamine & Urea Tie-in');

-- Pulp & Paper — Kemi Bio-Products Mill Expansion
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Kemi Bio-Products Mill Expansion', 'Finland', 'Pulp & Paper', 'Construction', 'high', 'Operator: Nordic Pulp Group | Kraft pulp: 1.5 Mtpa + packaging board | Start: 2027 | World-scale softwood pulp mill with new recovery boiler and bleaching plant',
    'DEMO:Pulp & Paper' , 'https://demo.miaoda.local/kemi-bio-products-mill-expansion', '2026-08-23',
    '316L, Duplex 2205, 254 SMO, 304L', 'Digester piping, bleach plant (ClO2), recovery boiler tubes, effluent treatment', 'Valmet, Andritz, AFRY'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Kemi Bio-Products Mill Expansion');

-- Pulp & Paper — Ornskoldsvik Dissolving Pulp Line
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ornskoldsvik Dissolving Pulp Line', 'Sweden', 'Pulp & Paper', 'EPC Award', 'high', 'Operator: Swedish Biorefinery Co | Dissolving pulp: 300 ktpa conversion | Start: 2027 | Conversion of paper pulp line to dissolving pulp for textile fiber; aggressive acid chemicals',
    'DEMO:Pulp & Paper' , 'https://demo.miaoda.local/ornskoldsvik-dissolving-pulp-line', '2026-08-23',
    '316L, 2205, Titanium, 254 SMO', 'Acid hydrolysis, evaporation, pulp drying, chemical recovery', 'Valmet, Sweco, Pöyry'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ornskoldsvik Dissolving Pulp Line');

-- Pulp & Paper — Sulawesi Greenfield Pulp Mill
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Sulawesi Greenfield Pulp Mill', 'Indonesia', 'Pulp & Paper', 'Approval', 'medium', 'Operator: Pacific Timber & Pulp | Bleached hardwood pulp: 1.0 Mtpa | Start: 2029 | Greenfield acacia pulp mill on Sulawesi with full chemical recovery island',
    'DEMO:Pulp & Paper' , 'https://demo.miaoda.local/sulawesi-greenfield-pulp-mill', '2026-08-23',
    '316L, 304L, Duplex 2205', 'Cooking and washing, bleach plant, recovery boiler, white liquor plant', 'China Light Industrial, Andritz, Sinoma'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Sulawesi Greenfield Pulp Mill');

-- Pulp & Paper — Richards Bay Tissue & Towel Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Richards Bay Tissue & Towel Plant', 'South Africa', 'Pulp & Paper', 'Planning', 'medium', 'Operator: KZN Paper Products | Tissue: 90 ktpa | Start: 2028 | New tissue mill with deinking plant using recycled furnish; stainless for stock prep and wet end',
    'DEMO:Pulp & Paper' , 'https://demo.miaoda.local/richards-bay-tissue-&-towel-plant', '2026-08-23',
    '316L, 304L, 2205', 'Stock preparation, deinking flotation cells, paper machine wet end, steam & condensate', 'Voith, Valmet, AMEC'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Richards Bay Tissue & Towel Plant');

-- Sugar — Khon Kaen Sugar Mill & Refinery Expansion
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Khon Kaen Sugar Mill & Refinery Expansion', 'Thailand', 'Sugar', 'Construction', 'high', 'Operator: Thai Sugar Group | Cane crush: 40,000 tcd | Refinery: 500 ktpa | Start: 2027 | Expansion adding a new diffusion train and back-end refinery; corrosion-resistant steel for juice processing',
    'DEMO:Sugar' , 'https://demo.miaoda.local/khon-kaen-sugar-mill-&-refinery-expansio', '2026-08-23',
    '316L, 304L, Duplex 2205', 'Juice heaters, evaporator bodies, vacuum pans, syrup piping, condensate system', 'Thyssenkrupp India, Bosch Projects, Hyundai'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Khon Kaen Sugar Mill & Refinery Expansion');

-- Sugar — Sao Paulo Flex Ethanol & Sugar Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Sao Paulo Flex Ethanol & Sugar Plant', 'Brazil', 'Sugar', 'EPC Award', 'high', 'Operator: Agroenergia Brasil | Cane crush: 30,000 tcd + 400 kL/day ethanol | Start: 2027 | Greenfield flex plant producing sugar and anhydrous ethanol with fermentation and distillation trains',
    'DEMO:Sugar' , 'https://demo.miaoda.local/sao-paulo-flex-ethanol-&-sugar-plant', '2026-08-23',
    '316L, 304L, Duplex 2205', 'Fermentation tanks, distillation columns, molasses storage, CIP systems', 'Dedini, Case New Holland, Codistil'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Sao Paulo Flex Ethanol & Sugar Plant');

-- Sugar — Karnataka Sugar Co-gen Boiler Upgrade
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Karnataka Sugar Co-gen Boiler Upgrade', 'India', 'Sugar', 'Procurement', 'medium', 'Operator: Karnataka Sugar Mills | Boiler: 120 tph HP bagasse boiler | Start: 2027 | High-pressure cogeneration boiler to boost power export from bagasse; superheater in alloy tubes',
    'DEMO:Sugar' , 'https://demo.miaoda.local/karnataka-sugar-co-gen-boiler-upgrade', '2026-08-23',
    '304H, 321H, 316L', 'Superheater coils, boiler bank tubes, ash handling, HP steam piping', 'Thermax, ISGEC, Walchandnagar'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Karnataka Sugar Co-gen Boiler Upgrade');

-- Sugar — Luzon Integrated Sugar Mill
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Luzon Integrated Sugar Mill', 'Philippines', 'Sugar', 'Planning', 'medium', 'Operator: Luzon Agro-Industrial Corp | Cane crush: 15,000 tcd | Start: 2029 | Integrated mill and refinery replacing aging capacity on Luzon island',
    'DEMO:Sugar' , 'https://demo.miaoda.local/luzon-integrated-sugar-mill', '2026-08-23',
    '304L, 316L, Duplex 2205', 'Juice clarification, evaporators, pans, syrup decolorization', 'Isgec, UPE, Thai Roong Ruang'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Luzon Integrated Sugar Mill');

-- Biopharma — Mainz mRNA Vaccine Facility 3
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Mainz mRNA Vaccine Facility 3', 'Germany', 'Biopharma', 'Construction', 'high', 'Operator: Biopharm Deutschland AG | mRNA drug substance & LNP fill-finish | Start: 2027 | Third commercial-scale mRNA facility; single-use systems with hygienic stainless utility loops',
    'DEMO:Biopharma' , 'https://demo.miaoda.local/mainz-mrna-vaccine-facility-3', '2026-08-23',
    '316L electro-polished, 1.4435, 254 SMO', 'WFI loops, clean steam, CIP/SIP, bioreactor jackets, LNP skid piping', 'M+W Group, Exyte, NNE'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Mainz mRNA Vaccine Facility 3');

-- Biopharma — Copenhagen Antibody DS Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Copenhagen Antibody DS Plant', 'Denmark', 'Biopharma', 'Procurement', 'high', 'Operator: Nordisk Biotech | mAb drug substance: 60,000 L | Start: 2027 | Large-scale mammalian cell culture plant with perfusion bioreactors',
    'DEMO:Biopharma' , 'https://demo.miaoda.local/copenhagen-antibody-ds-plant', '2026-08-23',
    '316L EP, 2205, AL-6XN', 'Harvest and purification skids, buffer prep, CIP, WFI distribution', 'NNE, Jacobs, Exyte'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Copenhagen Antibody DS Plant');

-- Biopharma — Singapore Viral Vector CDMO Line
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Singapore Viral Vector CDMO Line', 'Singapore', 'Biopharma', 'EPC Award', 'medium', 'Operator: VectorBio CDMO | Viral vector: AAV & lentivirus, 3 suites | Start: 2028 | Contract development and manufacturing facility for gene therapy vectors; BSL-2 containment',
    'DEMO:Biopharma' , 'https://demo.miaoda.local/singapore-viral-vector-cdmo-line', '2026-08-23',
    '316L EP, 304L, 254 SMO', 'BSC suites, containment drain system, kill tanks, gas supply manifolds', 'Jacobs, PM Group, Exyte'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Singapore Viral Vector CDMO Line');

-- Biopharma — Leiden Cell & Gene Therapy Campus
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Leiden Cell & Gene Therapy Campus', 'Netherlands', 'Biopharma', 'Planning', 'medium', 'Operator: Leiden Bio Campus | Cell therapy: autologous & allogeneic suites | Start: 2029 | Greenfield campus for cell therapy manufacturing with isolator-based suites',
    'DEMO:Biopharma' , 'https://demo.miaoda.local/leiden-cell-&-gene-therapy-campus', '2026-08-23',
    '316L EP, 304L, 2205', 'Isolator utilities, LN2 supply piping, clean utilities, waste decontamination', 'NNE, Royal HaskoningDHV, Exyte'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Leiden Cell & Gene Therapy Campus');

-- Nuclear — Poland Baltic AP1000 Nuclear Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Poland Baltic AP1000 Nuclear Plant', 'Poland', 'Nuclear', 'Approval', 'high', 'Operator: Polska Energia Jądrowa | Units: 3x AP1000, 3,750 MW | Start: 2032 | First nuclear plant on the Baltic coast; nuclear-grade stainless for reactor internals and BOP',
    'DEMO:Nuclear' , 'https://demo.miaoda.local/poland-baltic-ap1000-nuclear-plant', '2026-08-23',
    '316LN nuclear grade, 304L, 321H, Alloy 690', 'Reactor vessel internals, spent fuel pool liners, safety-related piping, steam generators', 'Westinghouse, Bechtel, GE Vernova'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Poland Baltic AP1000 Nuclear Plant');

-- Nuclear — Hokkaido Genkai-2 Restart Works
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Hokkaido Genkai-2 Restart Works', 'Japan', 'Nuclear', 'Procurement', 'medium', 'Operator: Kyushu Electric Power | Unit: 1,180 MW PWR restart | Start: 2028 | Safety-upgrade works required for restart under new regulations',
    'DEMO:Nuclear' , 'https://demo.miaoda.local/hokkaido-genkai-2-restart-works', '2026-08-23',
    '316LN, 304L, Inconel 690', 'ECCS strainers, filtered containment venting, seismic support steel, emergency DG piping', 'MHI, Hitachi-GE, Toshiba ESS'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Hokkaido Genkai-2 Restart Works');

-- Nuclear — Ontario SMR BWRX-300 Fleet
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ontario SMR BWRX-300 Fleet', 'Canada', 'Nuclear', 'Planning', 'medium', 'Operator: Ontario Power Generation | Units: 4x BWRX-300 SMR | Start: 2031 | First commercial SMR fleet in Canada at the Darlington site',
    'DEMO:Nuclear' , 'https://demo.miaoda.local/ontario-smr-bwrx-300-fleet', '2026-08-23',
    '316L, 304L, Alloy 600', 'RPV internals, containment liner, spent fuel storage, BOP piping', 'GE Hitachi, Aecon, BWXT'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ontario SMR BWRX-300 Fleet');

-- Nuclear — Czech Dukovany-II New Units
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Czech Dukovany-II New Units', 'Czech Republic', 'Nuclear', 'EPC Award', 'high', 'Operator: ČEZ | Units: 2x PWR, 2,400 MW | Start: 2032 | New build at Dukovany site; first nuclear plant construction in the country in decades',
    'DEMO:Nuclear' , 'https://demo.miaoda.local/czech-dukovany-ii-new-units', '2026-08-23',
    '316LN, 304L, Z2 CND 17-12', 'Primary circuit auxiliaries, RPV internals, containment penetrations, spent fuel pool', 'EDF, Framatome, KHNP'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Czech Dukovany-II New Units');

-- Geothermal — Hellisheidi Expansion Stage 4
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Hellisheidi Expansion Stage 4', 'Iceland', 'Geothermal', 'Construction', 'high', 'Operator: ON Power | Capacity: +60 MWe binary | Start: 2027 | Binary-cycle expansion at Hellisheidi using low-temperature brine from existing wells',
    'DEMO:Geothermal' , 'https://demo.miaoda.local/hellisheidi-expansion-stage-4', '2026-08-23',
    '316L, Duplex 2205, Titanium Gr.2, 254 SMO', 'Brine piping, ORC heat exchangers, reinjection wells, H2S abatement', 'Verkís, ÍSTAK, Mitsubishi Power'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Hellisheidi Expansion Stage 4');

-- Geothermal — Olkaria VII Geothermal Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Olkaria VII Geothermal Plant', 'Kenya', 'Geothermal', 'EPC Award', 'high', 'Operator: KenGen | Capacity: 140 MWe | Wells: 12 production | Start: 2028 | New steam field and plant at Olkaria; acidic steam condensate requires corrosion-resistant steels',
    'DEMO:Geothermal' , 'https://demo.miaoda.local/olkaria-vii-geothermal-plant', '2026-08-23',
    '316L, Duplex 2205, 254 SMO, Inconel 625', 'Two-phase gathering, separators, steam headers, condensate injection, cooling towers', 'Sinopec, SEPCO, Toyota Tsusho'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Olkaria VII Geothermal Plant');

-- Geothermal — Aydin Manisa Flash Plant U2
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Aydin Manisa Flash Plant U2', 'Turkey', 'Geothermal', 'Procurement', 'medium', 'Operator: EnerjiCo Türkiye | Capacity: 50 MWe flash + binary | Start: 2027 | Second unit at the Aydin concession; high non-condensable gas content drives alloy selection',
    'DEMO:Geothermal' , 'https://demo.miaoda.local/aydin-manisa-flash-plant-u2', '2026-08-23',
    '316L, Duplex 2205, Titanium Gr.2', 'Flash vessels, NCG compressors, brine reinjection, cooling water', 'Gürbağ, Ormat, Exergy'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Aydin Manisa Flash Plant U2');

-- Geothermal — New Zealand Taupo Deep Resource Pilot
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'New Zealand Taupo Deep Resource Pilot', 'New Zealand', 'Geothermal', 'Planning', 'medium', 'Operator: Taupo Geothermal Ltd | Capacity: 25 MWe supercritical pilot | Start: 2030 | Pilot project testing deep supercritical geothermal wells; extreme corrosion environment',
    'DEMO:Geothermal' , 'https://demo.miaoda.local/new-zealand-taupo-deep-resource-pilot', '2026-08-23',
    'Inconel 625, Hastelloy C-276, 254 SMO, Titanium', 'Deep well casings, supercritical wellhead, test separators, brine flash system', 'Mercury NZ, Jacobs, Beca'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'New Zealand Taupo Deep Resource Pilot');

-- Mining — Atacama Spence-SGO Copper Expansion
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Atacama Spence-SGO Copper Expansion', 'Chile', 'Mining', 'Construction', 'high', 'Operator: Minera Atacama | Copper concentrate: 250 ktpa + SX-EW expansion | Start: 2027 | Concentrator expansion with high-chloride seawater desalination feed for process water',
    'DEMO:Mining' , 'https://demo.miaoda.local/atacama-spence-sgo-copper-expansion', '2026-08-23',
    'Duplex 2205, Super Duplex 2507, 316L, Ceramic-lined steel', 'Slurry piping, flotation cells, SX mixer-settlers, seawater lift, acid plants', 'Bechtel, Fluor, Sigdo Koppers'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Atacama Spence-SGO Copper Expansion');

-- Mining — Pilbara Iron Ore Wet Plant 2
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Pilbara Iron Ore Wet Plant 2', 'Australia', 'Mining', 'EPC Award', 'high', 'Operator: Pilbara Iron Co | Iron ore: 60 Mtpa wet processing | Start: 2027 | Wet processing plant with desand, flotation and tailings thickening for lower-grade ores',
    'DEMO:Mining' , 'https://demo.miaoda.local/pilbara-iron-ore-wet-plant-2', '2026-08-23',
    'Duplex 2205, 316L, Bisalloy wear plate', 'Pump boxes, cyclones, thickener rakes, pipe launders, seawater systems', 'Clough, CPB Contractors, thyssenkrupp'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Pilbara Iron Ore Wet Plant 2');

-- Mining — Rudna Copper Smelter Modernization
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Rudna Copper Smelter Modernization', 'Poland', 'Mining', 'Procurement', 'medium', 'Operator: KGHM Polska Miedź | Copper: 450 ktpa flash smelting | Start: 2028 | Replacement of shaft furnace with flash smelting; sulfuric acid plant tie-in',
    'DEMO:Mining' , 'https://demo.miaoda.local/rudna-copper-smelter-modernization', '2026-08-23',
    '316L, 304L, Duplex 2205, Incoloy 825', 'Acid plant coolers, gas cleaning, matte launders, anode casting, electrolyte cells', 'Metso Outotec, Fluor, PBG'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Rudna Copper Smelter Modernization');

-- Mining — Saskatchewan Potash Solution Mine Phase 3
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Saskatchewan Potash Solution Mine Phase 3', 'Canada', 'Mining', 'Approval', 'medium', 'Operator: Prairie Potash Ltd | Potash: 3.0 Mtpa solution mining | Start: 2030 | Solution mining expansion with evaporation-crystallization trains for KCl',
    'DEMO:Mining' , 'https://demo.miaoda.local/saskatchewan-potash-solution-mine-phase-', '2026-08-23',
    '316L, 2205, AL-6XN, 254 SMO', 'Brine piping, crystallizers, centrifuge wash, dryer internals, KCl storage', 'Amec Foster Wheeler, Graham, K+S'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Saskatchewan Potash Solution Mine Phase 3');

-- Desalination — Ras Al Khair SWRO Phase 2
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Ras Al Khair SWRO Phase 2', 'Saudi Arabia', 'Desalination', 'Approval', 'high', 'Operator: SWCC | Capacity: 600,000 m3/day SWRO | Start: 2028 | Expansion of Ras Al Khair with membrane trains and energy recovery',
    'DEMO:Desalination' , 'https://demo.miaoda.local/ras-al-khair-swro-phase-2', '2026-08-23',
    'Super Duplex 2507, 254 SMO, 316L', 'HP brine piping, energy recovery, SWRO membranes, product water, chemical dosing', 'ACCIONA, Abengoa, Metito, Veolia'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Ras Al Khair SWRO Phase 2');

-- Desalination — Tocopilla Desalination Plant
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Tocopilla Desalination Plant', 'Chile', 'Desalination', 'EPC Award', 'high', 'Operator: Minera del Norte | Capacity: 2,600 L/s SWRO + brine | Start: 2027 | Desalination plant supplying copper mines in Antofagasta region',
    'DEMO:Desalination' , 'https://demo.miaoda.local/tocopilla-desalination-plant', '2026-08-23',
    'Super Duplex 2507, Duplex 2205, 904L', 'Seawater intake, cartridge filters, HP piping, brine outfall', 'IDE Technologies, Tedagua, Suez'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Tocopilla Desalination Plant');

-- Desalination — Alicante SWRO Expansion
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Alicante SWRO Expansion', 'Spain', 'Desalination', 'Construction', 'high', 'Operator: Acuamed | Capacity: +200,000 m3/day | Start: 2027 | Expansion of the Alicante II plant with photovoltaic power integration',
    'DEMO:Desalination' , 'https://demo.miaoda.local/alicante-swro-expansion', '2026-08-23',
    'Super Duplex 2507, 254 SMO, 316L', 'HP pumps, membrane racks, ERDs, chemical storage', 'Acciona Agua, FCC Aqualia, Befesa'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Alicante SWRO Expansion');

-- Desalination — Al Ghubra III Desalination
INSERT INTO public.projects
  (name, country, industry, phase, confidence, summary, source_name,
   source_url, source_date, stainless_steel, application, procurement_chain)
  SELECT
    'Al Ghubra III Desalination', 'Oman', 'Desalination', 'Procurement', 'medium', 'Operator: Oman Power & Water | Capacity: 300,000 m3/day MED-SWRO hybrid | Start: 2028 | Hybrid thermal and membrane plant at Al Ghubra with brine mining pilot',
    'DEMO:Desalination' , 'https://demo.miaoda.local/al-ghubra-iii-desalination', '2026-08-23',
    '316L, Duplex 2205, Titanium Gr.2, 254 SMO', 'MED evaporator tubes, SWRO HP piping, brine mining skid, product water storage', 'Suez, Wabag, ACWA Power'
  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = 'Al Ghubra III Desalination');

-- Step 2: 每个种子项目的 2 条候选事件（幂等：按项目+事件标题去重）
INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/north-gulf-lng-export-terminal',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'North Gulf LNG Export Terminal' AND summary = 'North Gulf LNG awards EPC contract for two liquefaction trains'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/north-gulf-lng-export-terminal',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'North Gulf LNG Export Terminal' AND summary = 'Long-lead items ordered for North Gulf LNG'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/mozambique-palma-south-lng-t3',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Mozambique Palma South LNG T3' AND summary = 'Train 3 EPC contract signed for Palma South LNG'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/mozambique-palma-south-lng-t3',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Mozambique Palma South LNG T3' AND summary = 'Palma South LNG opens tender for stainless piping packages'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/qatargas-east-expansion-lng',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Qatargas East Expansion LNG' AND summary = 'Qatargas East opens international tender for stainless steel plate'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/qatargas-east-expansion-lng',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Qatargas East Expansion LNG' AND summary = 'Qatargas East expansion clears FID'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/venture-pacific-flng-hull',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Venture Pacific FLNG Hull' AND summary = 'Venture Pacific launches FLNG FEED study'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:LNG', 'https://demo.miaoda.local/venture-pacific-flng-hull',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Venture Pacific FLNG Hull' AND summary = 'Venture Pacific FLNG environmental referral accepted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/daesan-ethylene-expansion-cracker',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Daesan Ethylene Expansion Cracker' AND summary = 'Daesan cracker achieves 65% construction progress'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/daesan-ethylene-expansion-cracker',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Daesan Ethylene Expansion Cracker' AND summary = 'Daesan cracker awards cast tube package'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/jubail-pdh/pp-complex-phase-2',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Jubail PDH/PP Complex Phase 2' AND summary = 'Jubail PDH/PP EPC contract signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/jubail-pdh/pp-complex-phase-2',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Jubail PDH/PP Complex Phase 2' AND summary = 'Jubail PDH selects reactor metallurgy'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/tuxpan-aromatics-btx-unit',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Tuxpan Aromatics BTX Unit' AND summary = 'Tuxpan BTX opens tender for heater tube bundles'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/tuxpan-aromatics-btx-unit',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Tuxpan Aromatics BTX Unit' AND summary = 'Tuxpan BTX foundation works complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/basra-ethane-cracker-&-derivatives',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Basra Ethane Cracker & Derivatives' AND summary = 'Basra cracker project obtains government approval'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Petrochemical', 'https://demo.miaoda.local/basra-ethane-cracker-&-derivatives',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Basra Ethane Cracker & Derivatives' AND summary = 'Basra cracker FEED refresh awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/ludwigshafen-chlor-alkali-replacement',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ludwigshafen Chlor-Alkali Replacement' AND summary = 'Chlor-alkali replacement reaches 70% completion'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/ludwigshafen-chlor-alkali-replacement',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ludwigshafen Chlor-Alkali Replacement' AND summary = 'Cell room piping in 254 SMO delivered'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/jurong-island-specialty-chemicals-hub',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Jurong Island Specialty Chemicals Hub' AND summary = 'Jurong hub awards high-alloy pipe package'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/jurong-island-specialty-chemicals-hub',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Jurong Island Specialty Chemicals Hub' AND summary = 'Jurong hub tenders clean utility skids'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/ningbo-epoxy-resin-train-3',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ningbo Epoxy Resin Train 3' AND summary = 'Ningbo epoxy Train 3 EPC awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/ningbo-epoxy-resin-train-3',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ningbo Epoxy Resin Train 3' AND summary = 'Ningbo epoxy Train 3 EIA approved'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/corpus-christi-green-methanol-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Corpus Christi Green Methanol Plant' AND summary = 'Green methanol FEED contract signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Chemical', 'https://demo.miaoda.local/corpus-christi-green-methanol-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Corpus Christi Green Methanol Plant' AND summary = 'Green methanol offtake MOU signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/vaca-muerta-ammonia-urea-greenfield',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Vaca Muerta Ammonia-Urea Greenfield' AND summary = 'Vaca Muerta ammonia-urea EPC awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/vaca-muerta-ammonia-urea-greenfield',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Vaca Muerta Ammonia-Urea Greenfield' AND summary = 'Urea synthesis metallurgy locked'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/ain-sokhna-phosphate-complex-npk',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ain Sokhna Phosphate Complex NPK' AND summary = 'Ain Sokhna NPK complex 55% complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/ain-sokhna-phosphate-complex-npk',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ain Sokhna Phosphate Complex NPK' AND summary = 'Ain Sokhna awards agitator and acid piping packages'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/kansas-nitrogen-revamp',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Kansas Nitrogen Revamp' AND summary = 'Kansas revamp orders reformer tubes'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/kansas-nitrogen-revamp',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Kansas Nitrogen Revamp' AND summary = 'Kansas revamp CO2 removal redesign approved'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/trinidad-melamine-&-urea-tie-in',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Trinidad Melamine & Urea Tie-in' AND summary = 'Trinidad melamine FEED launched'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Fertilizer', 'https://demo.miaoda.local/trinidad-melamine-&-urea-tie-in',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Trinidad Melamine & Urea Tie-in' AND summary = 'Trinidad melamine technology license signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/kemi-bio-products-mill-expansion',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Kemi Bio-Products Mill Expansion' AND summary = 'Kemi expansion 80% mechanical complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/kemi-bio-products-mill-expansion',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Kemi Bio-Products Mill Expansion' AND summary = 'Kemi mill orders ClO2 washer piping'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/ornskoldsvik-dissolving-pulp-line',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ornskoldsvik Dissolving Pulp Line' AND summary = 'Dissolving pulp conversion EPC signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/ornskoldsvik-dissolving-pulp-line',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ornskoldsvik Dissolving Pulp Line' AND summary = 'Hydrolysis stage metallurgy selected'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/sulawesi-greenfield-pulp-mill',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Sulawesi Greenfield Pulp Mill' AND summary = 'Sulawesi pulp mill environmental permit granted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/sulawesi-greenfield-pulp-mill',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Sulawesi Greenfield Pulp Mill' AND summary = 'Sulawesi pulp mill FEED awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/richards-bay-tissue-&-towel-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Richards Bay Tissue & Towel Plant' AND summary = 'Richards Bay tissue plant tenders paper machine'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Pulp & Paper', 'https://demo.miaoda.local/richards-bay-tissue-&-towel-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Richards Bay Tissue & Towel Plant' AND summary = 'Richards Bay tissue plant site works begin'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/khon-kaen-sugar-mill-&-refinery-expansio',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Khon Kaen Sugar Mill & Refinery Expansion' AND summary = 'Khon Kaen mill expansion 60% complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/khon-kaen-sugar-mill-&-refinery-expansio',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Khon Kaen Sugar Mill & Refinery Expansion' AND summary = 'Khon Kaen orders evaporator tube bundles'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/sao-paulo-flex-ethanol-&-sugar-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Sao Paulo Flex Ethanol & Sugar Plant' AND summary = 'Sao Paulo flex plant EPC signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/sao-paulo-flex-ethanol-&-sugar-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Sao Paulo Flex Ethanol & Sugar Plant' AND summary = 'Distillation columns specified in 316L'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/karnataka-sugar-co-gen-boiler-upgrade',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Karnataka Sugar Co-gen Boiler Upgrade' AND summary = 'Karnataka co-gen boiler tender closes'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/karnataka-sugar-co-gen-boiler-upgrade',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Karnataka Sugar Co-gen Boiler Upgrade' AND summary = 'Karnataka co-gen boiler island civil works done'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/luzon-integrated-sugar-mill',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Luzon Integrated Sugar Mill' AND summary = 'Luzon integrated mill FEED contracted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Sugar', 'https://demo.miaoda.local/luzon-integrated-sugar-mill',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Luzon Integrated Sugar Mill' AND summary = 'Luzon mill ECC application filed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/mainz-mrna-vaccine-facility-3',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Mainz mRNA Vaccine Facility 3' AND summary = 'Mainz mRNA Facility 3 tops out'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/mainz-mrna-vaccine-facility-3',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Mainz mRNA Vaccine Facility 3' AND summary = 'Mainz F3 awards hygienic utility piping'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/copenhagen-antibody-ds-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Copenhagen Antibody DS Plant' AND summary = 'Copenhagen antibody plant orders chromatography skids'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/copenhagen-antibody-ds-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Copenhagen Antibody DS Plant' AND summary = 'Copenhagen plant bioreactor order placed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/singapore-viral-vector-cdmo-line',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Singapore Viral Vector CDMO Line' AND summary = 'Singapore CDMO EPC awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/singapore-viral-vector-cdmo-line',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Singapore Viral Vector CDMO Line' AND summary = 'Singapore CDMO BSL-2 design approved'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/leiden-cell-&-gene-therapy-campus',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Leiden Cell & Gene Therapy Campus' AND summary = 'Leiden campus concept design awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Biopharma', 'https://demo.miaoda.local/leiden-cell-&-gene-therapy-campus',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Leiden Cell & Gene Therapy Campus' AND summary = 'Leiden campus anchor tenant signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/poland-baltic-ap1000-nuclear-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Poland Baltic AP1000 Nuclear Plant' AND summary = 'Poland nuclear plant environmental decision issued'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/poland-baltic-ap1000-nuclear-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Poland Baltic AP1000 Nuclear Plant' AND summary = 'Poland AP1000 EPC consortium formed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/hokkaido-genkai-2-restart-works',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Hokkaido Genkai-2 Restart Works' AND summary = 'Genkai-2 restart ECCS strainer tender'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/hokkaido-genkai-2-restart-works',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Hokkaido Genkai-2 Restart Works' AND summary = 'Genkai-2 NRA review progresses'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/ontario-smr-bwrx-300-fleet',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ontario SMR BWRX-300 Fleet' AND summary = 'Ontario SMR license to construct submitted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/ontario-smr-bwrx-300-fleet',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ontario SMR BWRX-300 Fleet' AND summary = 'Ontario SMR early site works contract'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/czech-dukovany-ii-new-units',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Czech Dukovany-II New Units' AND summary = 'Dukovany-II EPC preferred bidder announced'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Nuclear', 'https://demo.miaoda.local/czech-dukovany-ii-new-units',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Czech Dukovany-II New Units' AND summary = 'Dukovany-II site survey complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/hellisheidi-expansion-stage-4',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Hellisheidi Expansion Stage 4' AND summary = 'Hellisheidi Stage 4 turbine hall complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/hellisheidi-expansion-stage-4',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Hellisheidi Expansion Stage 4' AND summary = 'Hellisheidi orders brine heat exchangers'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/olkaria-vii-geothermal-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Olkaria VII Geothermal Plant' AND summary = 'Olkaria VII EPC contract signed'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/olkaria-vii-geothermal-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Olkaria VII Geothermal Plant' AND summary = 'Olkaria VII drilling campaign hits 60%'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/aydin-manisa-flash-plant-u2',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Aydin Manisa Flash Plant U2' AND summary = 'Aydin U2 turbine-generator ordered'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/aydin-manisa-flash-plant-u2',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Aydin Manisa Flash Plant U2' AND summary = 'Aydin U2 separator metallurgy study'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/new-zealand-taupo-deep-resource-pilot',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'New Zealand Taupo Deep Resource Pilot' AND summary = 'Taupo deep resource FEED study launched'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Geothermal', 'https://demo.miaoda.local/new-zealand-taupo-deep-resource-pilot',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'New Zealand Taupo Deep Resource Pilot' AND summary = 'Taupo deep drilling consent granted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/atacama-spence-sgo-copper-expansion',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Atacama Spence-SGO Copper Expansion' AND summary = 'Atacama concentrator 70% complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/atacama-spence-sgo-copper-expansion',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Atacama Spence-SGO Copper Expansion' AND summary = 'Atacama orders SX mixer-settlers'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/pilbara-iron-ore-wet-plant-2',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Pilbara Iron Ore Wet Plant 2' AND summary = 'Pilbara wet plant EPC awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/pilbara-iron-ore-wet-plant-2',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Pilbara Iron Ore Wet Plant 2' AND summary = 'Pilbara wet plant pump package ordered'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/rudna-copper-smelter-modernization',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Rudna Copper Smelter Modernization' AND summary = 'Rudna flash furnace equipment tender'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/rudna-copper-smelter-modernization',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Rudna Copper Smelter Modernization' AND summary = 'Rudna smelter modernization permit granted'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/saskatchewan-potash-solution-mine-phase-',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Saskatchewan Potash Solution Mine Phase 3' AND summary = 'Saskatchewan potash Phase 3 approved'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Mining', 'https://demo.miaoda.local/saskatchewan-potash-solution-mine-phase-',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Saskatchewan Potash Solution Mine Phase 3' AND summary = 'Saskatchewan potash crystallizer package bid'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/ras-al-khair-swro-phase-2',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ras Al Khair SWRO Phase 2' AND summary = 'Ras Al Khair Phase 2 RO package awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/ras-al-khair-swro-phase-2',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Ras Al Khair SWRO Phase 2' AND summary = 'Ras Al Khair HP piping specified 2507'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/tocopilla-desalination-plant',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Tocopilla Desalination Plant' AND summary = 'Tocopilla desal EPC awarded'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/tocopilla-desalination-plant',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Tocopilla Desalination Plant' AND summary = 'Tocopilla intake construction begins'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/alicante-swro-expansion',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Alicante SWRO Expansion' AND summary = 'Alicante expansion 65% complete'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/alicante-swro-expansion',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Alicante SWRO Expansion' AND summary = 'Alicante orders 2507 spools'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/al-ghubra-iii-desalination',
    '2026-07-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Al Ghubra III Desalination' AND summary = 'Al Ghubra III MED tube tender issued'
  );

INSERT INTO public.candidate_events
  (project_name_raw, event_type, country, summary, source_name, source_url,
   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,
   procurement_chain)
  SELECT {pn}, {et}, {c}, {es}, 'DEMO:Desalination', 'https://demo.miaoda.local/al-ghubra-iii-desalination',
    '2026-06-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}
  WHERE NOT EXISTS (
    SELECT 1 FROM public.candidate_events
    WHERE project_name_raw = 'Al Ghubra III Desalination' AND summary = 'Al Ghubra III brine mining pilot MOU'
  );

COMMIT;

-- 验证：
--   SELECT industry, COUNT(*) FROM public.projects GROUP BY industry ORDER BY 2 DESC;