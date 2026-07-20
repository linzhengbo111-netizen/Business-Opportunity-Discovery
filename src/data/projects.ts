/**
 * 静态示例数据 — 全球 FPSO 项目
 * 所有动态渲染（列表、统计、下拉选项、地图光点）的唯一数据源。
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

export const projects: Project[] = [
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

export interface CountryCoordinate {
  x: number;
  y: number;
}

export const countryCoordinates: Record<string, CountryCoordinate> = {
  Brazil: { x: 45, y: 78 },
  Guyana: { x: 35, y: 58 },
  Angola: { x: 62, y: 82 },
  Nigeria: { x: 58, y: 70 },
  UK: { x: 48, y: 35 },
  "Côte d'Ivoire": { x: 55, y: 65 },
};
