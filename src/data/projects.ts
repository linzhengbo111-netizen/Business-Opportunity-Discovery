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
    source: { name: "Petrobras", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Prosperity",
    country: "Guyana",
    flag: "🇬🇾",
    status: "Delivered",
    summary: "ExxonMobil Stabroek block Payara",
    source: { name: "SBM Offshore", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Agogo",
    country: "Angola",
    flag: "🇦🇴",
    status: "Under Construction",
    summary: "MODEC EPC contract for TotalEnergies",
    source: { name: "MODEC", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Zafiro",
    country: "Nigeria",
    flag: "🇳🇬",
    status: "Planned",
    summary: "Replacement for aging FPSO",
    source: { name: "World Oil", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Rosebank",
    country: "UK",
    flag: "🇬🇧",
    status: "Planned",
    summary:
      "Equinor's major North Sea development project featuring advanced subsea production systems and stainless steel topside modules",
    source: { name: "Offshore Energy", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Atlanta",
    country: "Brazil",
    flag: "🇧🇷",
    status: "Under Construction",
    summary: "Enauta's Santos Basin project",
    source: { name: "Offshore Magazine", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
  },
  {
    name: "FPSO Baobab",
    country: "Côte d'Ivoire",
    flag: "🇨🇮",
    status: "Planned",
    summary: "FEED phase targeting 2028 startup",
    source: { name: "Offshore Energy", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: "",
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
