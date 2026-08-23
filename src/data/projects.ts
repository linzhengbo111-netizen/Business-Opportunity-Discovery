/**
 * FPSO 项目类型定义 & 静态参考数据
 * 动态项目数据通过 Supabase projects 表获取；
 * sampleProjects 作为 Supabase 不可用时的回退数据。
 */

/** 置顶项目 — 商机看板 / 战报中心 / 项目时间线三页共用的优先排序清单。
 *  按此顺序排在最前；其余项目保持各自原有排序。
 *  匹配逻辑（含 canonical id 映射）见 project_aliases.ts 的 priority helpers。 */
export const PRIORITY_PROJECT_NAMES = [
  "FPSO ALMIRANTE TAMANDARE",
  "FPSO BACALHAU",
  "FPSO SEPETIBA",
] as const;

/* ------------------------------------------------------------------ */
/*  行业分类 — 单一数据源                                               */
/* ------------------------------------------------------------------ */

/** 全部行业垂直领域。projects.industry 列的取值域。
 *  FilterSidebar / DatabasePage / SettingsPage 订阅均从此处导入，
 *  不要在页面里再复制一份。 */
export const INDUSTRIES = [
  "FPSO",
  "Desalination",
  "LNG",
  "Petrochemical",
  "Chemical",
  "Fertilizer",
  "Pulp & Paper",
  "Sugar",
  "Biopharma",
  "Nuclear",
  "Geothermal",
  "Mining",
  /** 兜底桶 — 不属于以上任何垂直领域的不锈钢商机。 */
  "General Stainless",
] as const;

export type Industry = (typeof INDUSTRIES)[number];

/** 行业筛选的"不筛选"哨兵值。 */
export const ALL_INDUSTRIES = "All Industries";

/** 行业下拉框选项 = 哨兵值 + 全部行业。 */
export const INDUSTRY_OPTIONS = [ALL_INDUSTRIES, ...INDUSTRIES] as const;

/** 行业中文名。缺失的（FPSO / LNG 等通用缩写）直接显示英文。 */
const INDUSTRY_ZH: Record<string, string> = {
  Desalination: "海水淡化",
  Petrochemical: "石油化工",
  Chemical: "化工",
  Fertilizer: "化肥",
  "Pulp & Paper": "造纸",
  Sugar: "制糖",
  Biopharma: "生物制药",
  Nuclear: "核电",
  Geothermal: "地热",
  Mining: "采矿",
  "General Stainless": "其他不锈钢",
};

/** 行业下拉框显示文案，例如 `Desalination (海水淡化)`。 */
export function industryLabel(opt: string): string {
  const zh = INDUSTRY_ZH[opt];
  return zh ? `${opt} (${zh})` : opt;
}

/** Dashboard 主标题。跟随左侧行业筛选动态变化；
 *  All Industries 与兜底桶显示通用标题。 */
export function getIndustryTitle(industry: string): string {
  if (industry === "FPSO") return "全球 FPSO 项目商机挖掘";
  if (industry === "LNG") return "全球 LNG 项目商机挖掘";
  const zh = INDUSTRY_ZH[industry];
  if (zh && industry !== "General Stainless") return `全球${zh}项目商机挖掘`;
  return "全球商机挖掘";
}

/** 把任意 industry 值归一到已知行业；未知/空值归到 FPSO。
 *  历史行（industry 为 NULL）在 028 迁移中已回填为 FPSO，此处仅作防御。 */
export function normalizeIndustry(value: string | null | undefined): string {
  if (!value) return "FPSO";
  const hit = INDUSTRIES.find((i) => i.toLowerCase() === value.trim().toLowerCase());
  return hit ?? value.trim();
}

export interface ProjectSource {
  name: string;
  url: string;
  date: string;
}

export interface Project {
  name: string;
  country: string;
  flag: string;
  /** Lifecycle phase (9-phase taxonomy). Null = unknown, pending AI judgment.
   *  Legacy `status` rows are normalized client-side via project_phase.ts. */
  phase: string | null;
  summary: string;
  source: ProjectSource;
  stainlessSteel: string;
  application: string;
  industry?: string;
  confidence?: 'high' | 'medium' | 'low';
  procurementChain?: string;
  /** Technical specification fields — extracted from regulatory data or article text */
  waterDepthM?: number | null;
  oilCapacityBpd?: number | null;
  gasCapacityMmcmd?: number | null;
  hullType?: string | null;
  fieldName?: string | null;
  operatorName?: string | null;
  basin?: string | null;
  /** Stainless steel matching result (JSON string from recommendation_json column) */
  recommendationJson?: string | null;
  /** Row creation timestamp (Supabase created_at). Used for "last updated" display. */
  createdAt?: string | null;
  /** Corrosive media data (JSONB from Supabase). Parsed to { h2s, co2, sour_service, chloride, details }. */
  corrosiveMedia?: Record<string, unknown> | null;
}

/** Parsed material matching result */
export interface MaterialMatchResult {
  grades: string[];
  applications: string[];
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
}

export interface CountryCoordinate {
  x: number;
  y: number;
}

/** 静态示例数据 — Supabase 不可用或返回空时的回退数据源 */
export const sampleProjects: Project[] = [
  {
    name: "FPSO Maria Quitéria",
    country: "Brazil",
    flag: "🇧🇷",
    phase: "Construction",
    summary: "Petrobras pre-salt Santos Basin",
    source: { name: "Petrobras", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Prosperity",
    country: "Guyana",
    flag: "🇬🇾",
    phase: "Delivery",
    summary: "ExxonMobil Stabroek block Payara",
    source: { name: "SBM Offshore", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Agogo",
    country: "Angola",
    flag: "🇦🇴",
    phase: "EPC Award",
    summary: "MODEC EPC contract for TotalEnergies",
    source: { name: "MODEC", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Zafiro",
    country: "Nigeria",
    flag: "🇳🇬",
    phase: "Planning",
    summary: "Replacement for aging FPSO",
    source: { name: "World Oil", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Rosebank",
    country: "UK",
    flag: "🇬🇧",
    phase: "Design",
    summary:
      "Equinor's major North Sea development project featuring advanced subsea production systems and stainless steel topside modules",
    source: { name: "Offshore Energy", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Atlanta",
    country: "Brazil",
    flag: "🇧🇷",
    phase: "Construction",
    summary: "Enauta's Santos Basin project",
    source: { name: "Offshore Magazine", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
  {
    name: "FPSO Baobab",
    country: "Côte d'Ivoire",
    flag: "🇨🇮",
    phase: "Design",
    summary: "FEED phase targeting 2028 startup",
    source: { name: "Offshore Energy", url: "", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
  },
];

/**
 * 国家坐标映射 — 用于地图光点定位（静态地理数据）
 *
 * 所有坐标基于等矩形投影 (Equirectangular) 计算:
 *   x% = (longitude + 180) / 360 * 100
 *   y% = (90 - latitude)  / 180 * 100
 *
 * 底图: public/world-map.png (720×360, 2:1)
 */
export const countryCoordinates: Record<string, CountryCoordinate> = {
  // ---- 南美洲 ----
  Brazil:   { x: 35, y: 56 },  // ~10°S 55°W
  Guyana:   { x: 34, y: 47 },  //  ~5°N 59°W
  Suriname: { x: 34, y: 48 },  //  ~4°N 56°W

  // ---- 非洲 ----
  Angola:             { x: 55, y: 57 },  // ~12°S 18°E
  Nigeria:            { x: 52, y: 45 },  //  ~9°N  8°E
  "Côte d'Ivoire":   { x: 49, y: 46 },  //  ~8°N  5°W
  "Ivory Coast":      { x: 49, y: 46 },  //  same as Côte d'Ivoire (crawler uses both)
  Ghana:              { x: 50, y: 46 },  //  ~8°N  2°W (slightly right to avoid overlap)

  // ---- 欧洲 ----
  UK:     { x: 49, y: 19 },  // ~55°N 3°W
  Norway: { x: 53, y: 16 },  // ~62°N 10°E — estimated

  // ---- 亚洲 ----
  Indonesia: { x: 83, y: 51 },  //  ~2°S 118°E
  Singapore: { x: 79, y: 49 },  //  ~1°N 104°E
  Vietnam:   { x: 80, y: 42 },  // ~14°N 108°E
  China:     { x: 79, y: 31 },  // ~35°N 105°E — estimated
  Malaysia:  { x: 80, y: 48 },  //  ~4°N 109°E — estimated (incl. East Malaysia)
  India:     { x: 72, y: 38 },  // ~21°N 78°E — estimated

  // ---- 中东 ----
  Israel:         { x: 60,   y: 33   },  // ~31°N 35°E — estimated
  "Saudi Arabia": { x: 62.5, y: 36.7 },  // ~24°N 45°E
  UAE:            { x: 65,   y: 36.7 },  // ~24°N 54°E
  Qatar:          { x: 64.2, y: 35.9 },  // ~25°N 51°E
  Kuwait:         { x: 63.2, y: 33.7 },  // ~29°N 48°E
  Oman:           { x: 65.8, y: 38.3 },  // ~21°N 57°E

  // ---- 北美洲 ----
  USA:    { x: 25,   y: 34   },  // ~28°N 90°W — estimated (Gulf of Mexico)
  Canada: { x: 20.5, y: 18.8 },  // ~56°N 106°W
  Mexico: { x: 21.5, y: 36.9 },  // ~24°N 103°W

  // ---- 大洋洲 ----
  Australia:     { x: 87,   y: 64   },  // ~25°S 133°E — estimated
  "New Zealand": { x: 98.6, y: 72.7 },  // ~41°S 175°E

  // ---- 行业扩展新增 (028 seed) ----
  Chile:     { x: 30.4, y: 68.3 },  // ~33°S 71°W  — mining
  Peru:      { x: 29.2, y: 55.1 },  // ~9°S  75°W  — mining
  Argentina: { x: 32.3, y: 71.3 },  // ~38°S 64°W  — fertilizer
  Finland:   { x: 57.1, y: 15.6 },  // ~62°N 26°E  — pulp & paper
  Sweden:    { x: 55.2, y: 16.6 },  // ~60°N 19°E  — pulp & paper
  Germany:   { x: 52.9, y: 21.6 },  // ~51°N 10°E  — chemical / biopharma
  Spain:     { x: 49,   y: 27.5 },  // ~41°N 4°W   — desalination
  Poland:    { x: 55.3, y: 21.2 },  // ~52°N 19°E  — nuclear
  Iceland:   { x: 44.7, y: 13.9 },  // ~65°N 19°W  — geothermal
  Kenya:     { x: 60.5, y: 50   },  // ~0°N  38°E  — geothermal
  Egypt:     { x: 58.6, y: 35.1 },  // ~27°N 31°E  — desalination / fertilizer
  Turkey:    { x: 59.8, y: 28.4 },  // ~39°N 35°E  — geothermal
  Mozambique:     { x: 59.7, y: 60.6 },  // ~19°S 35°E  — LNG
  "Czech Republic": { x: 54.2, y: 22.2 },  // ~50°N 15°E  — nuclear
  Denmark:   { x: 52.5, y: 18.9 },  // ~56°N 9°E   — biopharma
  Japan:     { x: 88.4, y: 29.9 },  // ~36°N 138°E — nuclear
  "South Korea": { x: 85.5, y: 30.1 },  // ~36°N 128°E — petrochemical
  Thailand:  { x: 78.1, y: 41.2 },  // ~16°N 101°E — sugar
  Philippines: { x: 83.8, y: 42.8 },  // ~13°N 122°E — geothermal
  "South Africa": { x: 56.4, y: 67 },  // ~31°S 23°E — mining
  Netherlands: { x: 51.5, y: 21.1 },  // ~52°N 5°E  — biopharma
};

/**
 * Country name → ISO 3166-1 alpha-2 code mapping.
 * Used by countryToFlagEmoji() to generate flag emoji from country names
 * when the flag column is missing (candidate_events fallback path).
 * Mirrors crawler/crawl.py COUNTRY_CODE dictionary.
 */
const COUNTRY_CODE: Record<string, string> = {
  "Angola": "AO", "Argentina": "AR", "Australia": "AU", "Azerbaijan": "AZ",
  "Bahrain": "BH", "Brazil": "BR", "Cameroon": "CM", "Canada": "CA",
  "China": "CN", "Congo": "CG", "Cyprus": "CY", "Denmark": "DK",
  "Egypt": "EG", "Equatorial Guinea": "GQ", "Gabon": "GA", "Ghana": "GH",
  "Guyana": "GY", "India": "IN", "Indonesia": "ID", "Iran": "IR",
  "Iraq": "IQ", "Israel": "IL", "Japan": "JP",
  "Kazakhstan": "KZ", "Kuwait": "KW", "Libya": "LY", "Malaysia": "MY",
  "Mauritania": "MR", "Mexico": "MX", "Mozambique": "MZ", "Namibia": "NA",
  "Netherlands": "NL", "Nigeria": "NG", "Norway": "NO", "Oman": "OM",
  "Qatar": "QA", "Russia": "RU", "Saudi Arabia": "SA", "Senegal": "SN",
  "Singapore": "SG", "South Africa": "ZA", "South Korea": "KR",
  "Suriname": "SR", "Thailand": "TH", "Trinidad and Tobago": "TT",
  "Turkey": "TR", "UAE": "AE", "UK": "GB", "USA": "US",
  "Vietnam": "VN", "Yemen": "YE",
  "Côte d'Ivoire": "CI", "Ivory Coast": "CI",
  // 行业扩展新增 (028 seed)
  "Chile": "CL", "Peru": "PE", "Finland": "FI", "Sweden": "SE",
  "Germany": "DE", "Spain": "ES", "Poland": "PL", "Iceland": "IS",
  "Kenya": "KE", "Philippines": "PH", "New Zealand": "NZ",
  "Czech Republic": "CZ",
};

/**
 * Generate a flag emoji from a country name.
 * Converts ISO 3166-1 alpha-2 code to regional indicator symbols.
 * Returns empty string for unknown countries.
 */
export function countryToFlagEmoji(country: string): string {
  const code = COUNTRY_CODE[country];
  if (!code) return "";
  const offset = 0x1F1E6 - 65; // 'A' → regional indicator A
  return String.fromCodePoint(
    code.charCodeAt(0) + offset,
    code.charCodeAt(1) + offset,
  );
}

/**
 * Country name aliases — normalize variations to canonical form.
 * Mirrors crawler/crawl.py COUNTRY_ALIASES. Keep both in sync.
 *
 * Usage:
 *   import { COUNTRY_ALIASES } from "@/data/projects";
 *   const canonical = COUNTRY_ALIASES[rawName] ?? rawName;
 */
export const COUNTRY_ALIASES: Record<string, string> = {
  // USA
  "united states": "USA",
  "united states of america": "USA",
  "us": "USA",
  "u.s.": "USA",
  "u.s.a.": "USA",
  "america": "USA",

  // UK
  "united kingdom": "UK",
  "britain": "UK",
  "great britain": "UK",
  "england": "UK",
  "scotland": "UK",

  // UAE
  "united arab emirates": "UAE",
  "u.a.e.": "UAE",
  "emirates": "UAE",

  // Ivory Coast
  "côte d'ivoire": "Ivory Coast",
  "cote d'ivoire": "Ivory Coast",
  "côte d ivoire": "Ivory Coast",
  "cote divoire": "Ivory Coast",

  // Russia
  "russian federation": "Russia",

  // South Korea
  "korea": "South Korea",
  "republic of korea": "South Korea",

  // Congo
  "republic of congo": "Congo",
  "republic of the congo": "Congo",
  "congo-brazzaville": "Congo",
  "congo brazzaville": "Congo",
  "drc": "Congo",
  "democratic republic of congo": "Congo",
  "democratic republic of the congo": "Congo",

  // Trinidad and Tobago
  "trinidad": "Trinidad and Tobago",
  "trinidad & tobago": "Trinidad and Tobago",

  // Equatorial Guinea
  "eq guinea": "Equatorial Guinea",
  "eq. guinea": "Equatorial Guinea",

  // Saudi Arabia
  "saudi": "Saudi Arabia",
  "ksa": "Saudi Arabia",

  // Iran
  "islamic republic of iran": "Iran",

  // Netherlands
  "holland": "Netherlands",
  "the netherlands": "Netherlands",

  // Vietnam
  "viet nam": "Vietnam",

  // East Timor
  "east timor": "Timor-Leste",
  "timor leste": "Timor-Leste",

  // Myanmar
  "burma": "Myanmar",

  // Brunei
  "brunei darussalam": "Brunei",

  // Falklands
  "falklands": "Falkland Islands",
  "malvinas": "Falkland Islands",
  "islas malvinas": "Falkland Islands",

  // Papua New Guinea
  "png": "Papua New Guinea",

  // Philippines
  "the philippines": "Philippines",

  // Turkey
  "türkiye": "Turkey",
  "turkiye": "Turkey",

  // Venezuela
  "venezuela": "Venezuela",
};
