#!/usr/bin/env python3
"""
028 行业扩展种子数据 — 单一数据源。

两份产物：
  1. migrations/028_seed_all_industries.sql  — 存档/审计用（幂等,可在 SQL Editor 跑）
  2. 直接用 Supabase REST (anon key) 插入 — 立即生效

用法:
  python3 scripts/seed_all_industries.py            # 生成 SQL + 写库
  python3 scripts/seed_all_industries.py --sql-only # 只生成 SQL

数据约束（与需求一致）:
  - phase 全部为进行中（Planning/Approval/EPC Award/Procurement/Construction）
  - confidence 为 high/medium
  - 每个项目 2 条 candidate_events
  - 有 procurement_chain / summary / 行业技术描述
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

# 本地工具脚本 — macOS Python 常缺系统根证书,禁用证书校验
# （仍走 HTTPS,只是不校验链）。
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION_PATH = os.path.join(ROOT, "migrations", "028_seed_all_industries.sql")

# ---------------------------------------------------------------------------
# 种子项目定义（44 个项目 / 11 个行业，每行业 4 个）
#   name / country / phase / confidence / procurement_chain /
#   summary / stainless_steel / application / events[(type, summary, quote)]
#   每个 events 项生成一条 candidate_events 行。
#   项目名均为演示虚构名称（source_name 标记 DEMO:<行业>），后续可替换为真实数据。
# ---------------------------------------------------------------------------
SEED = [
    # ---------- LNG (4) ----------
    dict(industry="LNG", name="North Gulf LNG Export Terminal", country="USA",
         phase="Approval", confidence="high",
         chain="Bechtel, Chiyoda, Baker Hughes",
         summary="Operator: North Gulf LNG LLC | Capacity: 12.0 Mtpa | Trains: 2 | Refrigeration: Air Products C3-MR | Cold Box: Linde | Start: 2028 | Cryogenic stainless piping and duplex equipment for liquefaction trains",
         stainless="304L, 316L, 9% Ni steel, Super Duplex 2507 (seawater)",
         application="Cryogenic piping, cold boxes, LNG storage inner tanks, seawater cooling",
         events=[
             ("CONTRACT_AWARDED", "North Gulf LNG awards EPC contract for two liquefaction trains",
              "The project reached final investment decision with EPC award to a Bechtel-led consortium."),
             ("TECHNICAL_UPDATE", "Long-lead items ordered for North Gulf LNG",
              "Cold boxes and cryogenic ball valves are now in procurement, delivery expected within 14 months."),
         ]),
    dict(industry="LNG", name="Mozambique Palma South LNG T3", country="Mozambique",
         phase="EPC Award", confidence="high",
         chain="Saipem, Technip Energies, Mitsubishi Heavy",
         summary="Operator: TotalEnergies led JV | Capacity: 4.5 Mtpa | Train: 1 | Feed gas: Coral Sul offshore | Start: 2029 | Corrosive offshore gas requires duplex piping in amine and dehydration units",
         stainless="Duplex 2205, 316L, Incoloy 825",
         application="Acid gas removal, dehydration, HP flare, seawater intake",
         events=[
             ("CONTRACT_AWARDED", "Train 3 EPC contract signed for Palma South LNG",
              "JV signs $3.2bn EPC contract; module fabrication begins in Q1 next year."),
             ("PROCUREMENT_START", "Palma South LNG opens tender for stainless piping packages",
              "First procurement package covers 6,000 t of duplex and austenitic stainless pipe."),
         ]),
    dict(industry="LNG", name="Qatargas East Expansion LNG", country="Qatar",
         phase="Procurement", confidence="medium",
         chain="Technip Energies, Consolidated Contractors",
         summary="Operator: QatarEnergy | Capacity: 16.0 Mtpa | Trains: 2 | Refrigeration: AP-X hybrid | Start: 2030 | Expansion of the existing LNG complex with new utilities and cryogenic storage",
         stainless="304L, 9% Ni, Super Duplex 2507",
         application="LNG rundown lines, boil-off gas compressors, firewater piping",
         events=[
             ("TENDER_OPEN", "Qatargas East opens international tender for stainless steel plate",
              "Tender documents list 9% Ni plate for two 220,000 m3 full-containment tanks."),
             ("FID_ANNOUNCEMENT", "Qatargas East expansion clears FID",
              "Board approved the expansion; first steel expected on site within six months."),
         ]),
    dict(industry="LNG", name="Venture Pacific FLNG Hull", country="Australia",
         phase="Planning", confidence="medium",
         chain="MODEC, SBM Offshore, Samsung Heavy",
         summary="Operator: Venture Pacific Energy | Capacity: 3.0 Mtpa FLNG | Hull: 320m barge | Start: 2031 | FEED study evaluating floating liquefaction for marginal Browse Basin fields",
         stainless="316L, Duplex 2205, Inconel 625",
         application="FLNG topsides cryogenic piping, flare tower, seawater lift",
         events=[
             ("FEED_START", "Venture Pacific launches FLNG FEED study",
              "FEED contract awarded; concept selection expected within nine months."),
             ("REGULATORY", "Venture Pacific FLNG environmental referral accepted",
              "Regulator accepted the environmental referral, clearing the path to FEED completion."),
         ]),

    # ---------- Petrochemical (4) ----------
    dict(industry="Petrochemical", name="Daesan Ethylene Expansion Cracker", country="South Korea",
         phase="Construction", confidence="high",
         chain="Samsung Engineering, Tecnimont, Daelim",
         summary="Operator: Lotte Chemical | Feed: naphtha | Ethylene: 1.0 Mtpa | Start: 2027 | New mixed-feed cracker with downstream PE/PP units; furnace tubes in HK40/HP alloys",
         stainless="304H, 321H, HK-40, HP modified, Incoloy 800H",
         application="Cracking furnace tubes, quench exchangers, acetylene converter, product rundown",
         events=[
             ("CONSTRUCTION_UPDATE", "Daesan cracker achieves 65% construction progress",
              "Mechanical completion of furnace area expected next quarter; piping erection underway."),
             ("PROCUREMENT_START", "Daesan cracker awards cast tube package",
              "Furnace radiant and convection coil package awarded to two global suppliers."),
         ]),
    dict(industry="Petrochemical", name="Jubail PDH/PP Complex Phase 2", country="Saudi Arabia",
         phase="EPC Award", confidence="high",
         chain="McDermott, Hanwha, Tecnimont",
         summary="Operator: Gulf Polymers Co | Propane dehydrogenation 650 ktpa + PP 550 ktpa | Start: 2028 | High-temperature reactors and catalyst regeneration require heat-resistant stainless",
         stainless="304H, 321H, 347H, Duplex 2205",
         application="PDH reactor internals, regeneration loops, PP extrusion piping, cooling water",
         events=[
             ("CONTRACT_AWARDED", "Jubail PDH/PP EPC contract signed",
              "EPC lump-sum contract worth $1.8bn signed with international consortium."),
             ("TECHNICAL_UPDATE", "Jubail PDH selects reactor metallurgy",
              "Reactors specified with 347H stainless internals for 620°C service."),
         ]),
    dict(industry="Petrochemical", name="Tuxpan Aromatics BTX Unit", country="Mexico",
         phase="Procurement", confidence="medium",
         chain="ICA Fluor, Samsung Engineering",
         summary="Operator: Pemex JV | Capacity: paraxylene 800 ktpa | Feed: reformate | Start: 2028 | Aromatics complex revamp with new isomerization and CCR reformer units",
         stainless="316L, 321H, Duplex 2205, Incoloy 825",
         application="CCR reformer heater tubes, acid handling, benzene rundown lines",
         events=[
             ("TENDER_OPEN", "Tuxpan BTX opens tender for heater tube bundles",
              "Bids due next month for 9Cr-1Mo and 321H heater coils."),
             ("MILESTONE", "Tuxpan BTX foundation works complete",
              "Civil works finished; structural steel erection begins."),
         ]),
    dict(industry="Petrochemical", name="Basra Ethane Cracker & Derivatives", country="Iraq",
         phase="Approval", confidence="medium",
         chain="Petrofac, Tecnimont, Hyundai E&C",
         summary="Operator: Basra Petrochem Co | Ethylene: 1.5 Mtpa | Feed: ethane from South Gas Co | Start: 2030 | Grassroots cracker with PE units to monetize associated gas",
         stainless="304H, 321H, HP modified, 316L",
         application="Furnace coils, quench system, caustic wash, flare header",
         events=[
             ("FID_ANNOUNCEMENT", "Basra cracker project obtains government approval",
              "Council of Ministers approved the EPC funding envelope."),
             ("FEED_START", "Basra cracker FEED refresh awarded",
              "FEED verification contract awarded; EPC tender planned within 12 months."),
         ]),

    # ---------- Chemical (4) ----------
    dict(industry="Chemical", name="Ludwigshafen Chlor-Alkali Replacement", country="Germany",
         phase="Construction", confidence="high",
         chain="Thyssenkrupp Uhde, Bilfinger",
         summary="Operator: BASF | Chlorine: 600 ktpa membrane electrolysis | Start: 2027 | Replacement of mercury-cell plant with membrane technology; titanium and high-nickel alloys in electrolyzer loop",
         stainless="Titanium Gr.1/2, 254 SMO, 316L, Alloy 59",
         application="Electrolyzer cells, brine circuit, hypochlorite lines, caustic storage",
         events=[
             ("CONSTRUCTION_UPDATE", "Chlor-alkali replacement reaches 70% completion",
              "Electrolyzer hall mechanical completion targeted for end of year."),
             ("TECHNICAL_UPDATE", "Cell room piping in 254 SMO delivered",
              "First batch of 254 SMO spools for brine service arrived on site."),
         ]),
    dict(industry="Chemical", name="Jurong Island Specialty Chemicals Hub", country="Singapore",
         phase="Procurement", confidence="high",
         chain="Worley, Samsung C&T, Rotary Engineering",
         summary="Operator: SpecialtyChem Asia | Products: pharma intermediates, aroma chemicals | Start: 2027 | Multi-train specialty chemicals hub with high-alloy process piping for corrosive intermediates",
         stainless="316L, 904L, 254 SMO, Hastelloy C-276",
         application="Reactor jacketing, solvent recovery, effluent treatment, clean utilities",
         events=[
             ("PROCUREMENT_START", "Jurong hub awards high-alloy pipe package",
              "Framework agreement signed for 904L and 254 SMO piping across all trains."),
             ("TENDER_OPEN", "Jurong hub tenders clean utility skids",
              "WFI and clean steam skid tender closes this month."),
         ]),
    dict(industry="Chemical", name="Ningbo Epoxy Resin Train 3", country="China",
         phase="EPC Award", confidence="medium",
         chain="Sinopec Engineering, China Huanqiu",
         summary="Operator: Ningbo Epoxy Co | Epoxy resin: 150 ktpa | Feed: ECH/BPA | Start: 2027 | Third production train with chlorine-related processes requiring corrosion-resistant equipment",
         stainless="316L, Duplex 2205, Titanium, Alloy 20",
         application="ECH reactors, caustic scrubbers, waste acid concentration",
         events=[
             ("CONTRACT_AWARDED", "Ningbo epoxy Train 3 EPC awarded",
              "Domestic EPC consortium signed for the new train."),
             ("REGULATORY", "Ningbo epoxy Train 3 EIA approved",
              "Environmental approval granted; site preparation started."),
         ]),
    dict(industry="Chemical", name="Corpus Christi Green Methanol Plant", country="USA",
         phase="Planning", confidence="medium",
         chain="KBR, Technip Energies, Fluor",
         summary="Operator: Gulf Methanol Renewables | Methanol: 900 ktpa from green H2 + captured CO2 | Start: 2029 | First-of-kind e-methanol plant; electrolysis at 30 bar requires duplex and super-austenitic alloys",
         stainless="Duplex 2205, 254 SMO, 316L",
         application="HP electrolysis, methanol synthesis loop, CO2 capture column internals",
         events=[
             ("FEED_START", "Green methanol FEED contract signed",
              "FEED underway; final investment decision targeted in 18 months."),
             ("PARTNERSHIP", "Green methanol offtake MOU signed",
              "Long-term offtake MOU signed with European chemical distributor."),
         ]),

    # ---------- Fertilizer (4) ----------
    dict(industry="Fertilizer", name="Vaca Muerta Ammonia-Urea Greenfield", country="Argentina",
         phase="EPC Award", confidence="high",
         chain="Tecnimont, Petrofac, SACDE",
         summary="Operator: YPF Agro JV | Ammonia: 1.2 Mtpa | Urea: 2.1 Mtpa | Feed: Vaca Muerta gas | Start: 2028 | Greenfield nitrogen complex with high-pressure synthesis loops in urea-grade alloys",
         stainless="316L Urea grade, 25Cr22Ni2Mo (Safurex), 304L, Duplex 2205",
         application="Urea synthesis loop, strippers, HP condensate, ammonium carbamate piping",
         events=[
             ("CONTRACT_AWARDED", "Vaca Muerta ammonia-urea EPC awarded",
              "$2.4bn lump-sum EPC contract signed; piling begins in two months."),
             ("TECHNICAL_UPDATE", "Urea synthesis metallurgy locked",
              "Final design selects Safurex-class 25Cr22Ni2Mo for carbamate service."),
         ]),
    dict(industry="Fertilizer", name="Ain Sokhna Phosphate Complex NPK", country="Egypt",
         phase="Construction", confidence="high",
         chain="Orascom Construction, Tecnimont, Wuhuan",
         summary="Operator: Egyptian Fertilizer Co | NPK/DAP: 1.0 Mtpa | Feed: phosphate rock + sulfur | Start: 2027 | Phosphate complex with phosphoric acid and DAP granulation trains",
         stainless="904L, Alloy 20, 316L, Duplex 2205",
         application="Phosphoric acid evaporators, slurry piping, scrubbers, sulfuric acid dilution",
         events=[
             ("CONSTRUCTION_UPDATE", "Ain Sokhna NPK complex 55% complete",
              "Acid storage tanks erected; granulation building roof closed."),
             ("PROCUREMENT_START", "Ain Sokhna awards agitator and acid piping packages",
              "Tenders awarded for rubber-lined and alloy slurry piping."),
         ]),
    dict(industry="Fertilizer", name="Kansas Nitrogen Revamp", country="USA",
         phase="Procurement", confidence="medium",
         chain="KBR, Brown & Root, Zachry",
         summary="Operator: Mid-America Nitrogen | Ammonia: 700 ktpa revamp | Start: 2027 | Debottlenecking of primary reformer and CO2 removal with new alloy components",
         stainless="321H, Incoloy 800H, 316L, Duplex 2205",
         application="Reformer tubes, waste heat boiler, CO2 absorber internals, letdown valves",
         events=[
             ("PROCUREMENT_START", "Kansas revamp orders reformer tubes",
              "800H reformer tubes on order; delivery slots confirmed."),
             ("TECHNICAL_UPDATE", "Kansas revamp CO2 removal redesign approved",
              "New absorber internals specified in 316L."),
         ]),
    dict(industry="Fertilizer", name="Trinidad Melamine & Urea Tie-in", country="Trinidad and Tobago",
         phase="Planning", confidence="medium",
         chain="Saipem, Toyo Engineering, Massy Wood",
         summary="Operator: Trinidad Nitrogen Holdings | Melamine: 80 ktpa tie-in to existing urea | Start: 2029 | Value-add melamine unit using urea feed; HP section in urea-grade stainless",
         stainless="316L Urea grade, 25Cr22Ni2Mo, 304L",
         application="Melamine reactor, off-gas scrubbing, urea tie-in piping",
         events=[
             ("FEED_START", "Trinidad melamine FEED launched",
              "FEED study contracted; EPC tender planned next year."),
             ("PARTNERSHIP", "Trinidad melamine technology license signed",
              "Licensor selected for low-pressure melamine process."),
         ]),

    # ---------- Pulp & Paper (4) ----------
    dict(industry="Pulp & Paper", name="Kemi Bio-Products Mill Expansion", country="Finland",
         phase="Construction", confidence="high",
         chain="Valmet, Andritz, AFRY",
         summary="Operator: Nordic Pulp Group | Kraft pulp: 1.5 Mtpa + packaging board | Start: 2027 | World-scale softwood pulp mill with new recovery boiler and bleaching plant",
         stainless="316L, Duplex 2205, 254 SMO, 304L",
         application="Digester piping, bleach plant (ClO2), recovery boiler tubes, effluent treatment",
         events=[
             ("CONSTRUCTION_UPDATE", "Kemi expansion 80% mechanical complete",
              "Recovery boiler hydro test passed; bleach plant equipment arriving."),
             ("PROCUREMENT_START", "Kemi mill orders ClO2 washer piping",
              "254 SMO piping package awarded for D0-stage bleaching."),
         ]),
    dict(industry="Pulp & Paper", name="Ornskoldsvik Dissolving Pulp Line", country="Sweden",
         phase="EPC Award", confidence="high",
         chain="Valmet, Sweco, Pöyry",
         summary="Operator: Swedish Biorefinery Co | Dissolving pulp: 300 ktpa conversion | Start: 2027 | Conversion of paper pulp line to dissolving pulp for textile fiber; aggressive acid chemicals",
         stainless="316L, 2205, Titanium, 254 SMO",
         application="Acid hydrolysis, evaporation, pulp drying, chemical recovery",
         events=[
             ("CONTRACT_AWARDED", "Dissolving pulp conversion EPC signed",
              "Conversion contract awarded; shutdown integration planned for Q2."),
             ("TECHNICAL_UPDATE", "Hydrolysis stage metallurgy selected",
              "Hot acid hydrolysis loop specified in titanium and 254 SMO."),
         ]),
    dict(industry="Pulp & Paper", name="Sulawesi Greenfield Pulp Mill", country="Indonesia",
         phase="Approval", confidence="medium",
         chain="China Light Industrial, Andritz, Sinoma",
         summary="Operator: Pacific Timber & Pulp | Bleached hardwood pulp: 1.0 Mtpa | Start: 2029 | Greenfield acacia pulp mill on Sulawesi with full chemical recovery island",
         stainless="316L, 304L, Duplex 2205",
         application="Cooking and washing, bleach plant, recovery boiler, white liquor plant",
         events=[
             ("REGULATORY", "Sulawesi pulp mill environmental permit granted",
              "Environmental approval obtained after two-year review."),
             ("FEED_START", "Sulawesi pulp mill FEED awarded",
              "FEED and basic engineering contracts signed."),
         ]),
    dict(industry="Pulp & Paper", name="Richards Bay Tissue & Towel Plant", country="South Africa",
         phase="Planning", confidence="medium",
         chain="Voith, Valmet, AMEC",
         summary="Operator: KZN Paper Products | Tissue: 90 ktpa | Start: 2028 | New tissue mill with deinking plant using recycled furnish; stainless for stock prep and wet end",
         stainless="316L, 304L, 2205",
         application="Stock preparation, deinking flotation cells, paper machine wet end, steam & condensate",
         events=[
             ("TENDER_OPEN", "Richards Bay tissue plant tenders paper machine",
              "Machine supplier tender launched; selection expected this quarter."),
             ("MILESTONE", "Richards Bay tissue plant site works begin",
              "Site levelling and piling for the mill building started."),
         ]),

    # ---------- Sugar (4) ----------
    dict(industry="Sugar", name="Khon Kaen Sugar Mill & Refinery Expansion", country="Thailand",
         phase="Construction", confidence="high",
         chain="Thyssenkrupp India, Bosch Projects, Hyundai",
         summary="Operator: Thai Sugar Group | Cane crush: 40,000 tcd | Refinery: 500 ktpa | Start: 2027 | Expansion adding a new diffusion train and back-end refinery; corrosion-resistant steel for juice processing",
         stainless="316L, 304L, Duplex 2205",
         application="Juice heaters, evaporator bodies, vacuum pans, syrup piping, condensate system",
         events=[
             ("CONSTRUCTION_UPDATE", "Khon Kaen mill expansion 60% complete",
              "New evaporator station erected; pan floor steelwork underway."),
             ("PROCUREMENT_START", "Khon Kaen orders evaporator tube bundles",
              "Stainless tube bundles for falling-film evaporators on order."),
         ]),
    dict(industry="Sugar", name="Sao Paulo Flex Ethanol & Sugar Plant", country="Brazil",
         phase="EPC Award", confidence="high",
         chain="Dedini, Case New Holland, Codistil",
         summary="Operator: Agroenergia Brasil | Cane crush: 30,000 tcd + 400 kL/day ethanol | Start: 2027 | Greenfield flex plant producing sugar and anhydrous ethanol with fermentation and distillation trains",
         stainless="316L, 304L, Duplex 2205",
         application="Fermentation tanks, distillation columns, molasses storage, CIP systems",
         events=[
             ("CONTRACT_AWARDED", "Sao Paulo flex plant EPC signed",
              "Turnkey contract awarded for mill, fermentation and distillation."),
             ("TECHNICAL_UPDATE", "Distillation columns specified in 316L",
              "Three-column distillation train with 316L internals confirmed."),
         ]),
    dict(industry="Sugar", name="Karnataka Sugar Co-gen Boiler Upgrade", country="India",
         phase="Procurement", confidence="medium",
         chain="Thermax, ISGEC, Walchandnagar",
         summary="Operator: Karnataka Sugar Mills | Boiler: 120 tph HP bagasse boiler | Start: 2027 | High-pressure cogeneration boiler to boost power export from bagasse; superheater in alloy tubes",
         stainless="304H, 321H, 316L",
         application="Superheater coils, boiler bank tubes, ash handling, HP steam piping",
         events=[
             ("TENDER_OPEN", "Karnataka co-gen boiler tender closes",
              "HP boiler supply tender closed; technical evaluation in progress."),
             ("MILESTONE", "Karnataka co-gen boiler island civil works done",
              "Boiler house foundation completed ahead of equipment delivery."),
         ]),
    dict(industry="Sugar", name="Luzon Integrated Sugar Mill", country="Philippines",
         phase="Planning", confidence="medium",
         chain="Isgec, UPE, Thai Roong Ruang",
         summary="Operator: Luzon Agro-Industrial Corp | Cane crush: 15,000 tcd | Start: 2029 | Integrated mill and refinery replacing aging capacity on Luzon island",
         stainless="304L, 316L, Duplex 2205",
         application="Juice clarification, evaporators, pans, syrup decolorization",
         events=[
             ("FEED_START", "Luzon integrated mill FEED contracted",
              "Consultancy contract signed for mill configuration study."),
             ("REGULATORY", "Luzon mill ECC application filed",
              "Environmental compliance certificate application submitted."),
         ]),

    # ---------- Biopharma (4) ----------
    dict(industry="Biopharma", name="Mainz mRNA Vaccine Facility 3", country="Germany",
         phase="Construction", confidence="high",
         chain="M+W Group, Exyte, NNE",
         summary="Operator: Biopharm Deutschland AG | mRNA drug substance & LNP fill-finish | Start: 2027 | Third commercial-scale mRNA facility; single-use systems with hygienic stainless utility loops",
         stainless="316L electro-polished, 1.4435, 254 SMO",
         application="WFI loops, clean steam, CIP/SIP, bioreactor jackets, LNP skid piping",
         events=[
             ("CONSTRUCTION_UPDATE", "Mainz mRNA Facility 3 tops out",
              "Building envelope complete; cleanroom fit-out 40% done."),
             ("PROCUREMENT_START", "Mainz F3 awards hygienic utility piping",
              "Orbital-welded 316L piping package for WFI/clean steam awarded."),
         ]),
    dict(industry="Biopharma", name="Copenhagen Antibody DS Plant", country="Denmark",
         phase="Procurement", confidence="high",
         chain="NNE, Jacobs, Exyte",
         summary="Operator: Nordisk Biotech | mAb drug substance: 60,000 L | Start: 2027 | Large-scale mammalian cell culture plant with perfusion bioreactors",
         stainless="316L EP, 2205, AL-6XN",
         application="Harvest and purification skids, buffer prep, CIP, WFI distribution",
         events=[
             ("PROCUREMENT_START", "Copenhagen antibody plant orders chromatography skids",
              "Purification skid contracts signed with two vendors."),
             ("TECHNICAL_UPDATE", "Copenhagen plant bioreactor order placed",
              "Six 10,000 L perfusion bioreactors ordered."),
         ]),
    dict(industry="Biopharma", name="Singapore Viral Vector CDMO Line", country="Singapore",
         phase="EPC Award", confidence="medium",
         chain="Jacobs, PM Group, Exyte",
         summary="Operator: VectorBio CDMO | Viral vector: AAV & lentivirus, 3 suites | Start: 2028 | Contract development and manufacturing facility for gene therapy vectors; BSL-2 containment",
         stainless="316L EP, 304L, 254 SMO",
         application="BSC suites, containment drain system, kill tanks, gas supply manifolds",
         events=[
             ("CONTRACT_AWARDED", "Singapore CDMO EPC awarded",
              "Design-build contract signed for the three-suite vector facility."),
             ("REGULATORY", "Singapore CDMO BSL-2 design approved",
              "Containment design review passed with health authority."),
         ]),
    dict(industry="Biopharma", name="Leiden Cell & Gene Therapy Campus", country="Netherlands",
         phase="Planning", confidence="medium",
         chain="NNE, Royal HaskoningDHV, Exyte",
         summary="Operator: Leiden Bio Campus | Cell therapy: autologous & allogeneic suites | Start: 2029 | Greenfield campus for cell therapy manufacturing with isolator-based suites",
         stainless="316L EP, 304L, 2205",
         application="Isolator utilities, LN2 supply piping, clean utilities, waste decontamination",
         events=[
             ("FEED_START", "Leiden campus concept design awarded",
              "Concept design for the 40,000 m2 campus underway."),
             ("PARTNERSHIP", "Leiden campus anchor tenant signed",
              "First tenant MOU signed for two allogeneic manufacturing suites."),
         ]),

    # ---------- Nuclear (4) ----------
    dict(industry="Nuclear", name="Poland Baltic AP1000 Nuclear Plant", country="Poland",
         phase="Approval", confidence="high",
         chain="Westinghouse, Bechtel, GE Vernova",
         summary="Operator: Polska Energia Jądrowa | Units: 3x AP1000, 3,750 MW | Start: 2032 | First nuclear plant on the Baltic coast; nuclear-grade stainless for reactor internals and BOP",
         stainless="316LN nuclear grade, 304L, 321H, Alloy 690",
         application="Reactor vessel internals, spent fuel pool liners, safety-related piping, steam generators",
         events=[
             ("REGULATORY", "Poland nuclear plant environmental decision issued",
              "Environmental decision for the Baltic site became final."),
             ("CONTRACT_AWARDED", "Poland AP1000 EPC consortium formed",
              "Westinghouse-Bechtel consortium signed the delivery agreement."),
         ]),
    dict(industry="Nuclear", name="Hokkaido Genkai-2 Restart Works", country="Japan",
         phase="Procurement", confidence="medium",
         chain="MHI, Hitachi-GE, Toshiba ESS",
         summary="Operator: Kyushu Electric Power | Unit: 1,180 MW PWR restart | Start: 2028 | Safety-upgrade works required for restart under new regulations",
         stainless="316LN, 304L, Inconel 690",
         application="ECCS strainers, filtered containment venting, seismic support steel, emergency DG piping",
         events=[
             ("TENDER_OPEN", "Genkai-2 restart ECCS strainer tender",
              "Tender issued for replacement ECCS sump strainers."),
             ("MILESTONE", "Genkai-2 NRA review progresses",
              "Regulator completed the second round of design review."),
         ]),
    dict(industry="Nuclear", name="Ontario SMR BWRX-300 Fleet", country="Canada",
         phase="Planning", confidence="medium",
         chain="GE Hitachi, Aecon, BWXT",
         summary="Operator: Ontario Power Generation | Units: 4x BWRX-300 SMR | Start: 2031 | First commercial SMR fleet in Canada at the Darlington site",
         stainless="316L, 304L, Alloy 600",
         application="RPV internals, containment liner, spent fuel storage, BOP piping",
         events=[
             ("REGULATORY", "Ontario SMR license to construct submitted",
              "License application submitted to the CNSC."),
             ("FEED_START", "Ontario SMR early site works contract",
              "Early site preparation contract awarded."),
         ]),
    dict(industry="Nuclear", name="Czech Dukovany-II New Units", country="Czech Republic",
         phase="EPC Award", confidence="high",
         chain="EDF, Framatome, KHNP",
         summary="Operator: ČEZ | Units: 2x PWR, 2,400 MW | Start: 2032 | New build at Dukovany site; first nuclear plant construction in the country in decades",
         stainless="316LN, 304L, Z2 CND 17-12",
         application="Primary circuit auxiliaries, RPV internals, containment penetrations, spent fuel pool",
         events=[
             ("CONTRACT_AWARDED", "Dukovany-II EPC preferred bidder announced",
              "Government announced preferred bidder for the two-unit contract."),
             ("TECHNICAL_UPDATE", "Dukovany-II site survey complete",
              "Geological and seismic survey finished; license process launched."),
         ]),

    # ---------- Geothermal (4) ----------
    dict(industry="Geothermal", name="Hellisheidi Expansion Stage 4", country="Iceland",
         phase="Construction", confidence="high",
         chain="Verkís, ÍSTAK, Mitsubishi Power",
         summary="Operator: ON Power | Capacity: +60 MWe binary | Start: 2027 | Binary-cycle expansion at Hellisheidi using low-temperature brine from existing wells",
         stainless="316L, Duplex 2205, Titanium Gr.2, 254 SMO",
         application="Brine piping, ORC heat exchangers, reinjection wells, H2S abatement",
         events=[
             ("CONSTRUCTION_UPDATE", "Hellisheidi Stage 4 turbine hall complete",
              "ORC turbine delivery scheduled for next quarter."),
             ("PROCUREMENT_START", "Hellisheidi orders brine heat exchangers",
              "Plate heat exchangers in titanium ordered for the binary loop."),
         ]),
    dict(industry="Geothermal", name="Olkaria VII Geothermal Plant", country="Kenya",
         phase="EPC Award", confidence="high",
         chain="Sinopec, SEPCO, Toyota Tsusho",
         summary="Operator: KenGen | Capacity: 140 MWe | Wells: 12 production | Start: 2028 | New steam field and plant at Olkaria; acidic steam condensate requires corrosion-resistant steels",
         stainless="316L, Duplex 2205, 254 SMO, Inconel 625",
         application="Two-phase gathering, separators, steam headers, condensate injection, cooling towers",
         events=[
             ("CONTRACT_AWARDED", "Olkaria VII EPC contract signed",
              "EPC contract for steam field and power plant awarded."),
             ("MILESTONE", "Olkaria VII drilling campaign hits 60%",
              "Eight of twelve production wells drilled and tested."),
         ]),
    dict(industry="Geothermal", name="Aydin Manisa Flash Plant U2", country="Turkey",
         phase="Procurement", confidence="medium",
         chain="Gürbağ, Ormat, Exergy",
         summary="Operator: EnerjiCo Türkiye | Capacity: 50 MWe flash + binary | Start: 2027 | Second unit at the Aydin concession; high non-condensable gas content drives alloy selection",
         stainless="316L, Duplex 2205, Titanium Gr.2",
         application="Flash vessels, NCG compressors, brine reinjection, cooling water",
         events=[
             ("PROCUREMENT_START", "Aydin U2 turbine-generator ordered",
              "Turbine island equipment ordered for delivery in ten months."),
             ("TECHNICAL_UPDATE", "Aydin U2 separator metallurgy study",
              "Separator internals upgraded to 2205 after corrosion audit."),
         ]),
    dict(industry="Geothermal", name="New Zealand Taupo Deep Resource Pilot", country="New Zealand",
         phase="Planning", confidence="medium",
         chain="Mercury NZ, Jacobs, Beca",
         summary="Operator: Taupo Geothermal Ltd | Capacity: 25 MWe supercritical pilot | Start: 2030 | Pilot project testing deep supercritical geothermal wells; extreme corrosion environment",
         stainless="Inconel 625, Hastelloy C-276, 254 SMO, Titanium",
         application="Deep well casings, supercritical wellhead, test separators, brine flash system",
         events=[
             ("FEED_START", "Taupo deep resource FEED study launched",
              "Pre-FEED study of supercritical wellhead equipment underway."),
             ("REGULATORY", "Taupo deep drilling consent granted",
              "Resource consent approved for two deep wells to 4 km."),
         ]),

    # ---------- Mining (4) ----------
    dict(industry="Mining", name="Atacama Spence-SGO Copper Expansion", country="Chile",
         phase="Construction", confidence="high",
         chain="Bechtel, Fluor, Sigdo Koppers",
         summary="Operator: Minera Atacama | Copper concentrate: 250 ktpa + SX-EW expansion | Start: 2027 | Concentrator expansion with high-chloride seawater desalination feed for process water",
         stainless="Duplex 2205, Super Duplex 2507, 316L, Ceramic-lined steel",
         application="Slurry piping, flotation cells, SX mixer-settlers, seawater lift, acid plants",
         events=[
             ("CONSTRUCTION_UPDATE", "Atacama concentrator 70% complete",
              "Ball mill installed; flotation rows being erected."),
             ("PROCUREMENT_START", "Atacama orders SX mixer-settlers",
              "Electrolytic stainless settlers ordered for the SX plant."),
         ]),
    dict(industry="Mining", name="Pilbara Iron Ore Wet Plant 2", country="Australia",
         phase="EPC Award", confidence="high",
         chain="Clough, CPB Contractors, thyssenkrupp",
         summary="Operator: Pilbara Iron Co | Iron ore: 60 Mtpa wet processing | Start: 2027 | Wet processing plant with desand, flotation and tailings thickening for lower-grade ores",
         stainless="Duplex 2205, 316L, Bisalloy wear plate",
         application="Pump boxes, cyclones, thickener rakes, pipe launders, seawater systems",
         events=[
             ("CONTRACT_AWARDED", "Pilbara wet plant EPC awarded",
              "EPC contract signed for the 60 Mtpa wet processing plant."),
             ("TECHNICAL_UPDATE", "Pilbara wet plant pump package ordered",
              "Slurry pump package specified with 2205 wet ends."),
         ]),
    dict(industry="Mining", name="Rudna Copper Smelter Modernization", country="Poland",
         phase="Procurement", confidence="medium",
         chain="Metso Outotec, Fluor, PBG",
         summary="Operator: KGHM Polska Miedź | Copper: 450 ktpa flash smelting | Start: 2028 | Replacement of shaft furnace with flash smelting; sulfuric acid plant tie-in",
         stainless="316L, 304L, Duplex 2205, Incoloy 825",
         application="Acid plant coolers, gas cleaning, matte launders, anode casting, electrolyte cells",
         events=[
             ("TENDER_OPEN", "Rudna flash furnace equipment tender",
              "International tender for flash smelting equipment launched."),
             ("REGULATORY", "Rudna smelter modernization permit granted",
              "Integrated permit obtained; demolition of old furnace begins."),
         ]),
    dict(industry="Mining", name="Saskatchewan Potash Solution Mine Phase 3", country="Canada",
         phase="Approval", confidence="medium",
         chain="Amec Foster Wheeler, Graham, K+S",
         summary="Operator: Prairie Potash Ltd | Potash: 3.0 Mtpa solution mining | Start: 2030 | Solution mining expansion with evaporation-crystallization trains for KCl",
         stainless="316L, 2205, AL-6XN, 254 SMO",
         application="Brine piping, crystallizers, centrifuge wash, dryer internals, KCl storage",
         events=[
             ("FID_ANNOUNCEMENT", "Saskatchewan potash Phase 3 approved",
              "Board approved funding for the solution mine expansion."),
             ("TECHNICAL_UPDATE", "Saskatchewan potash crystallizer package bid",
              "Vendors shortlisted for four-effect crystallizer trains."),
         ]),

    # ---------- Desalination (4) — 原 DB 中该行业为 0 行，一并补种子
    dict(industry="Desalination", name="Ras Al Khair SWRO Phase 2", country="Saudi Arabia",
         phase="Approval", confidence="high",
         chain="ACCIONA, Abengoa, Metito, Veolia",
         summary="Operator: SWCC | Capacity: 600,000 m3/day SWRO | Start: 2028 | Expansion of Ras Al Khair with membrane trains and energy recovery",
         stainless="Super Duplex 2507, 254 SMO, 316L",
         application="HP brine piping, energy recovery, SWRO membranes, product water, chemical dosing",
         events=[
             ("CONTRACT_AWARDED", "Ras Al Khair Phase 2 RO package awarded",
              "RO membrane package awarded; construction start in three months."),
             ("TECHNICAL_UPDATE", "Ras Al Khair HP piping specified 2507",
              "High-pressure brine headers specified in super duplex 2507."),
         ]),
    dict(industry="Desalination", name="Tocopilla Desalination Plant", country="Chile",
         phase="EPC Award", confidence="high",
         chain="IDE Technologies, Tedagua, Suez",
         summary="Operator: Minera del Norte | Capacity: 2,600 L/s SWRO + brine | Start: 2027 | Desalination plant supplying copper mines in Antofagasta region",
         stainless="Super Duplex 2507, Duplex 2205, 904L",
         application="Seawater intake, cartridge filters, HP piping, brine outfall",
         events=[
             ("CONTRACT_AWARDED", "Tocopilla desal EPC awarded",
              "BOOT contract signed; water purchase agreement effective."),
             ("MILESTONE", "Tocopilla intake construction begins",
              "Marine works for the 3.5 km intake pipeline started."),
         ]),
    dict(industry="Desalination", name="Alicante SWRO Expansion", country="Spain",
         phase="Construction", confidence="high",
         chain="Acciona Agua, FCC Aqualia, Befesa",
         summary="Operator: Acuamed | Capacity: +200,000 m3/day | Start: 2027 | Expansion of the Alicante II plant with photovoltaic power integration",
         stainless="Super Duplex 2507, 254 SMO, 316L",
         application="HP pumps, membrane racks, ERDs, chemical storage",
         events=[
             ("CONSTRUCTION_UPDATE", "Alicante expansion 65% complete",
              "Membrane racks installed; commissioning planned in six months."),
             ("PROCUREMENT_START", "Alicante orders 2507 spools",
              "Remaining high-pressure spool packages awarded."),
         ]),
    dict(industry="Desalination", name="Al Ghubra III Desalination", country="Oman",
         phase="Procurement", confidence="medium",
         chain="Suez, Wabag, ACWA Power",
         summary="Operator: Oman Power & Water | Capacity: 300,000 m3/day MED-SWRO hybrid | Start: 2028 | Hybrid thermal and membrane plant at Al Ghubra with brine mining pilot",
         stainless="316L, Duplex 2205, Titanium Gr.2, 254 SMO",
         application="MED evaporator tubes, SWRO HP piping, brine mining skid, product water storage",
         events=[
             ("TENDER_OPEN", "Al Ghubra III MED tube tender issued",
              "Tender issued for 3,000 km of titanium and 316L evaporator tubing."),
             ("PARTNERSHIP", "Al Ghubra III brine mining pilot MOU",
              "MOU signed for magnesium extraction from brine reject."),
         ]),
]

# ---------------------------------------------------------------------------
# SQL 生成
# ---------------------------------------------------------------------------

def sql_lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def build_migration():
    lines = []
    a = lines.append
    a("-- ============================================================================")
    a("-- 028_seed_all_industries.sql")
    a("-- 行业扩展种子数据：11 个行业 × 4 个演示项目 + 每项目 2 条 candidate_events。")
    a("-- 幂等：所有 INSERT 均带 WHERE NOT EXISTS 守卫，可重复执行。")
    a("-- 同时回填 industry IS NULL 的历史行为 'FPSO'（与前端 normalizeIndustry 一致）。")
    a("-- 演示项目 source_name 统一标记 DEMO:<行业>，后续可用真实数据替换。")
    a("-- ============================================================================")
    a("")
    a("BEGIN;")
    a("")
    a("-- Step 0: 历史行回填 — 前端将 NULL 当 FPSO 处理，落库保持一致。")
    a("UPDATE public.projects SET industry = 'FPSO' WHERE industry IS NULL;")
    a("")
    a("-- Step 1: 种子项目")
    for p in SEED:
        a("-- %s — %s" % (p["industry"], p["name"]))
        a("INSERT INTO public.projects")
        a("  (name, country, industry, phase, confidence, summary, source_name,")
        a("   source_url, source_date, stainless_steel, application, procurement_chain)")
        a("  SELECT")
        a("    {n}, {c}, {i}, {ph}, {cf}, {s},".format(
            n=sql_lit(p["name"]), c=sql_lit(p["country"]), i=sql_lit(p["industry"]),
            ph=sql_lit(p["phase"]), cf=sql_lit(p["confidence"]), s=sql_lit(p["summary"])))
        a("    'DEMO:%s' , 'https://demo.miaoda.local/%s', '2026-08-23'," % (
            p["industry"], p["name"].lower().replace(" ", "-")[:40]))
        a("    {ss}, {ap}, {pc}".format(
            ss=sql_lit(p["stainless"]), ap=sql_lit(p["application"]), pc=sql_lit(p["chain"])))
        a("  WHERE NOT EXISTS (SELECT 1 FROM public.projects WHERE name = {n});".format(n=sql_lit(p["name"])))
        a("")
    a("-- Step 2: 每个种子项目的 2 条候选事件（幂等：按项目+事件标题去重）")
    for p in SEED:
        for idx, (etype, esum, quote) in enumerate(p["events"]):
            a("INSERT INTO public.candidate_events")
            a("  (project_name_raw, event_type, country, summary, source_name, source_url,")
            a("   publication_date, fetched_at, evidence_quote, review_status, confidence, phase,")
            a("   procurement_chain)")
            a("  SELECT {pn}, {et}, {c}, {es}, 'DEMO:%s', 'https://demo.miaoda.local/%s'," % (
                p["industry"], p["name"].lower().replace(" ", "-")[:40]))
            a("    '2026-0%d-15', now(), {q}, 'accepted', {cf}, {ph}, {pc}" % (7 - idx,))
            a("  WHERE NOT EXISTS (")
            a("    SELECT 1 FROM public.candidate_events")
            a("    WHERE project_name_raw = {pn} AND summary = {es}".format(
                pn=sql_lit(p["name"]), es=sql_lit(esum)))
            a("  );")
            a("")
    a("COMMIT;")
    a("")
    a("-- 验证：")
    a("--   SELECT industry, COUNT(*) FROM public.projects GROUP BY industry ORDER BY 2 DESC;")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# REST 插入
# ---------------------------------------------------------------------------

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def quote_lit(v):
    """PostgREST in.() 列表元素 — 引号保留，值编码。"""
    return '"' + urllib.parse.quote(v, safe="") + '"'

def rest(method, path, payload=None):
    supabase_url = os.environ["VITE_SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["VITE_SUPABASE_ANON_KEY"]
    url = supabase_url + "/rest/v1/" + path
    req = urllib.request.Request(url, method=method)
    req.add_header("apikey", anon_key)
    req.add_header("Authorization", "Bearer " + anon_key)
    req.add_header("Content-Type", "application/json")
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Length", str(len(data)))
    else:
        data = None
    try:
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, data, context=_SSL_CTX) as resp:
                    body = resp.read().decode()
                    return json.loads(body) if body.strip() else None
            except (urllib.error.HTTPError, ConnectionError, TimeoutError) as e:
                if isinstance(e, urllib.error.HTTPError):
                    detail = e.read().decode()
                    if attempt == 3:
                        raise RuntimeError("%s %s -> %s %s" % (method, path, e.code, detail[:300]))
                elif attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError("%s %s -> %s %s" % (method, path, e.code, detail[:300]))


def fetch_one(path, params):
    return rest("GET", path + "?" + "&".join("%s=%s" % (k, v) for k, v in params.items()))


def seed_via_rest(dry_run=False):
    names = [p["name"] for p in SEED]
    event_keys = [(p["name"], esum) for p in SEED for (_, esum, _) in p["events"]]

    # 幂等检查一次完成：in.() 过滤只拉种子相关行。
    existing_projects = set(
        r["name"] for r in rest("GET",
            "projects?select=name&name=in.(%s)" % ",".join(quote_lit(n) for n in names)))
    existing_events = set()
    for chunk in chunks([esum for (_, esum, _) in
                         [e for p in SEED for e in p["events"]]], 40):
        rows = rest("GET",
            "candidate_events?select=project_name_raw,summary&summary=in.(%s)" %
            ",".join(quote_lit(s) for s in chunk))
        existing_events.update((r.get("project_name_raw"), r.get("summary")) for r in rows)

    inserted_projects, inserted_events = 0, 0
    skipped_projects, skipped_events = 0, 0
    for p in SEED:
        name = p["name"]
        if name in existing_projects:
            skipped_projects += 1
        else:
            payload = {
                "name": name,
                "country": p["country"],
                "industry": p["industry"],
                "phase": p["phase"],
                "confidence": p["confidence"],
                "summary": p["summary"],
                "source_name": "DEMO:" + p["industry"],
                "source_url": "https://demo.miaoda.local/" + name.lower().replace(" ", "-")[:40],
                "source_date": "2026-08-23",
                "stainless_steel": p["stainless"],
                "application": p["application"],
                "procurement_chain": p["chain"],
                "flag": "",
            }
            if dry_run:
                inserted_projects += 1
                print("  [dry] project:", name)
            else:
                rest("POST", "projects", payload)
                inserted_projects += 1
                print("  + project:", name)

        for idx, (etype, esum, quote) in enumerate(p["events"]):
            if (name, esum) in existing_events:
                skipped_events += 1
                continue
            payload = {
                "project_name_raw": name,
                "canonical_project_id": name.lower().replace(" ", "-"),
                "event_type": etype,
                "country": p["country"],
                "summary": esum,
                "source_name": "DEMO:" + p["industry"],
                "source_url": "https://demo.miaoda.local/" + name.lower().replace(" ", "-")[:40],
                "publication_date": "2026-0%d-15" % (7 - idx),
                "fetched_at": "2026-08-23T00:00:00Z",
                "evidence_quote": quote,
                "review_status": "accepted",
                "confidence": p["confidence"],
                "phase": p["phase"],
                "procurement_chain": p["chain"],
            }
            if dry_run:
                inserted_events += 1
            else:
                rest("POST", "candidate_events", payload)
                inserted_events += 1
                print("  + event   : %s" % esum[:70])
    print("projects: %d inserted, %d skipped | events: %d inserted, %d skipped" % (
        inserted_projects, skipped_projects, inserted_events, skipped_events))


def backfill_null_industry():
    """industry IS NULL 的历史行回填为 FPSO。"""
    ids = []
    offset = 0
    while True:
        rows = rest("GET",
            "projects?select=id&industry=is.null&order=id&limit=1000&offset=%d" % offset)
        if not rows:
            break
        ids.extend(r["id"] for r in rows)
        if len(rows) < 1000:
            break
        offset += 1000
    if not ids:
        print("NULL industry backfill: 0 rows")
        return
    # REST UPDATE 无法用 is.null 过滤,按 id 批量更新。
    updated = 0
    for i in range(0, len(ids), 200):
        part = ids[i:i + 200]
        rest("PATCH", "projects?id=in.(%s)" % ",".join(map(str, part)),
             {"industry": "FPSO"})
        updated += len(part)
    print("NULL industry backfill: %d rows -> FPSO" % updated)


def main():
    sql_only = "--sql-only" in sys.argv
    dry_run = "--dry-run" in sys.argv

    sql = build_migration()
    with open(MIGRATION_PATH, "w") as f:
        f.write(sql)
    print("wrote %s" % MIGRATION_PATH)

    if sql_only:
        return

    # 读取 .env（KEY=VALUE 行，容忍注释）
    env_path = os.path.join(ROOT, ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k in ("VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
                os.environ.setdefault(k, v.strip())

    if "VITE_SUPABASE_URL" not in os.environ or "VITE_SUPABASE_ANON_KEY" not in os.environ:
        print("missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY")
        sys.exit(1)

    if not dry_run:
        backfill_null_industry()
    seed_via_rest(dry_run=dry_run)


if __name__ == "__main__":
    main()
