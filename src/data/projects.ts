/**
 * FPSO 项目类型定义 & 静态参考数据
 * 动态项目数据通过 Supabase projects 表获取；
 * sampleProjects 作为 Supabase 不可用时的回退数据。
 */

export interface ProjectSource {
  name: string;
  url: string;
  date: string;
}

export interface Project {
  name: string;
  country: string;
  flag: string;
  status: string;
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
    status: "Under Construction",
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
    status: "Delivered",
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
    status: "Under Construction",
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
    status: "Planned",
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
    status: "Planned",
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
    status: "Under Construction",
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
    status: "Planned",
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
  UK: { x: 49, y: 19 },  // ~55°N 3°W

  // ---- 亚洲 ----
  Indonesia: { x: 83, y: 51 },  //  ~2°S 118°E
  Singapore: { x: 79, y: 49 },  //  ~1°N 104°E
  Vietnam:   { x: 80, y: 42 },  // ~14°N 108°E
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
