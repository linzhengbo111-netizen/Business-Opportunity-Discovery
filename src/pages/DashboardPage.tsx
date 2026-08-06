/**
 * Business Opportunity Discovery
 * 深色数据终端风格单页面：全球 FPSO 项目不锈钢商机挖掘系统
 * 数据源：Supabase projects + candidate_events 合并显示
 */

import { useEffect, useMemo, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis,
} from "recharts";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project } from "@/data/projects";
import { countryCoordinates, sampleProjects, countryToFlagEmoji, COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";

interface Stats {
  total: number;
  active: number;
  planned: number;
}

function getStats(projects: Project[]): Stats {
  return {
    total: projects.length,
    active: projects.filter((p) => p.status === "Under Construction").length,
    planned: projects.filter((p) => p.status === "Planned").length,
  };
}

function getUniqueCountries(projects: Project[]): string[] {
  const set = new Set<string>();
  for (const p of projects) {
    set.add(p.country.trim());
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

function getCountryFlag(projects: Project[], country: string): string {
  const found = projects.find((p) => p.country.trim() === country.trim() && p.flag);
  return found?.flag ?? "";
}

function statusColorClass(status: string): string {
  switch (status) {
    case "Under Construction":
      return "text-fpso-blue";
    case "Delivered":
      return "text-fpso-green";
    case "Planned":
      return "text-fpso-orange";
    default:
      return "text-fpso-muted";
  }
}

function statusDotClass(status: string): string {
  switch (status) {
    case "Under Construction":
      return "bg-fpso-blue";
    case "Delivered":
      return "bg-fpso-green";
    case "Planned":
      return "bg-fpso-orange";
    default:
      return "bg-fpso-muted";
  }
}

function confidenceBadgeClass(confidence: string): string {
  switch (confidence) {
    case "high":
      return "bg-fpso-green/15 text-fpso-green";
    case "medium":
      return "bg-fpso-orange/15 text-fpso-orange";
    case "low":
      return "bg-fpso-muted/15 text-fpso-muted";
    default:
      return "bg-fpso-muted/15 text-fpso-muted";
  }
}

/** Apply country name alias with case-insensitive fallback. */
function normalizeCountry(raw: string): string {
  if (!raw) return "Unknown";
  const trimmed = raw.trim();
  return COUNTRY_ALIASES[trimmed] ?? COUNTRY_ALIASES[trimmed.toLowerCase()] ?? trimmed;
}

/** Map a raw Supabase row (snake_case columns) to the camelCase Project interface. */
function mapRowToProject(row: Record<string, unknown>): Project {
  const rawCountry = String(row.country ?? "").trim();
  const country = normalizeCountry(rawCountry);
  const rawName = String(row.name ?? "");
  // Normalize project name through canonical alias system for dedup
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
  const confidence = String(row.confidence ?? "medium") as "high" | "medium" | "low";
  return {
    name,
    country,
    flag: String(row.flag ?? ""),
    status: String(row.status ?? ""),
    summary: String(row.summary ?? ""),
    source: {
      name: String(row.source_name ?? ""),
      url: String(row.source_url ?? ""),
      date: String(row.source_date ?? ""),
    },
    stainlessSteel: String(row.stainless_steel ?? ""),
    application: String(row.application ?? ""),
    industry: String(row.industry ?? "FPSO"),
    confidence,
    procurementChain: String(row.procurement_chain ?? ""),
  };
}

/** Map a candidate_events row to the Project interface for fallback display.
 *  candidate_events lacks flag, status, stainless_steel, application — we provide defaults. */
function mapCandidateToProject(row: Record<string, unknown>): Project {
  const rawCountry = String(row.country ?? "").trim();
  const country = normalizeCountry(rawCountry);
  const sourceDate = String(row.publication_date || row.fetched_at || "");
  const rawName = String(row.project_name_raw ?? "");
  // Normalize project name through canonical alias system for dedup
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
  const confidence = String(row.confidence ?? "medium") as "high" | "medium" | "low";
  return {
    name,
    country,
    flag: countryToFlagEmoji(country),
    status: "Unknown",
    summary: String(row.summary ?? ""),
    source: {
      name: String(row.source_name ?? ""),
      url: String(row.source_url ?? ""),
      date: sourceDate.slice(0, 10),
    },
    stainlessSteel: "",
    application: "",
    industry: "FPSO",
    confidence,
    procurementChain: "",
  };
}

const INDUSTRY_OPTIONS = [
  "All Industries",
  "FPSO",
  "Desalination",
  "LNG",
  "General Stainless",
] as const;

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCountry, setSelectedCountry] = useState("All Countries");
  const [selectedIndustry, setSelectedIndustry] = useState("All Industries");
  const [selectedConfidence, setSelectedConfidence] = useState("High");
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const { version, status: connectionStatus } = useProjectRealtime();

  // ---- 从 Supabase 获取项目数据 ----
  useEffect(() => {
    console.log("[Dashboard] === Starting data fetch ===");
    console.log("[Dashboard] supabase client: initialized");

    console.log(
      "地图已更换，若光点位置偏移，请调整 src/data/projects.ts 中的 countryCoordinates 百分比。"
    );

    let cancelled = false;

    async function fetchTable(tableName: string): Promise<Project[]> {
      const start = performance.now();
      const { data, error } = await supabase.from(tableName).select("*");
      const elapsed = (performance.now() - start).toFixed(0);

      if (error) {
        console.error(`[Dashboard] '${tableName}' fetch FAILED (${elapsed}ms):`, error.message);
        return [];
      }

      const mapped = (data ?? []).map(
        tableName === "projects" ? mapRowToProject : mapCandidateToProject,
      );
      console.log(`[Dashboard] '${tableName}' fetch OK (${elapsed}ms): ${mapped.length} rows`);
      return mapped;
    }

    async function loadData() {
      // ---- Fetch BOTH tables in parallel (always) ----
      const [projectEntries, candidateEntries] = await Promise.all([
        fetchTable("projects"),
        fetchTable("candidate_events"),
      ]);

      if (cancelled) return;

      // ---- Merge: projects entries first (richer data), then non-overlapping candidates ----
      const seen = new Set<string>();
      // Dedup key: canonical project ID if matched, otherwise normalized raw name
      function dedupKey(p: Project): string {
        const canonical = normalizeProjectName(p.name);
        return canonical ?? p.name.trim().toLowerCase().replace(/^fpso\s+/i, "");
      }

      const merged: Project[] = [];

      for (const p of projectEntries) {
        const key = dedupKey(p);
        if (key && !seen.has(key)) {
          seen.add(key);
          merged.push(p);
        }
      }

      for (const c of candidateEntries) {
        const key = dedupKey(c);
        if (key && !seen.has(key)) {
          seen.add(key);
          merged.push(c);
        }
      }

      console.log(
        `[Dashboard] Merge: ${projectEntries.length} projects + ${candidateEntries.length} candidates = ${merged.length} unique`,
      );

      if (merged.length > 0) {
        console.log("[Dashboard] ✅ Using live Supabase data:");
        console.table(merged.map((p) => ({ name: p.name, country: p.country, status: p.status })));
        if (!cancelled) setProjects(merged);
      } else {
        console.warn("[Dashboard] Both tables EMPTY. Falling back to sampleProjects.");
        if (!cancelled) setProjects(sampleProjects);
      }
    }

    loadData().finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [version]);

  // ---- 派生数据 ----
  const countries = useMemo(() => getUniqueCountries(projects), [projects]);

  const filteredProjects = useMemo(() => {
    let result = projects;
    if (selectedCountry !== "All Countries") {
      result = result.filter((p) => p.country.trim() === selectedCountry);
    }
    if (selectedIndustry !== "All Industries") {
      result = result.filter((p) => (p.industry ?? "FPSO") === selectedIndustry);
    }
    if (selectedConfidence !== "All") {
      result = result.filter(
        (p) => (p.confidence ?? "medium") === selectedConfidence.toLowerCase(),
      );
    }
    return result;
  }, [projects, selectedCountry, selectedIndustry, selectedConfidence]);

  const filteredStats = useMemo(() => getStats(filteredProjects), [filteredProjects]);

  // 图表数据
  const countryChartData = useMemo(() => {
    const count: Record<string, number> = {};
    for (const p of filteredProjects) {
      const c = p.country.trim();
      count[c] = (count[c] ?? 0) + 1;
    }
    return Object.entries(count)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [filteredProjects]);

  const statusChartData = useMemo(() => {
    const order = ["Under Construction", "Delivered", "Planned"];
    const count: Record<string, number> = {};
    for (const p of filteredProjects) {
      const s = p.status || "Unknown";
      count[s] = (count[s] ?? 0) + 1;
    }
    return order
      .filter((s) => count[s] != null)
      .map((s) => ({ name: s, value: count[s] }))
      .concat(count["Unknown"] ? [{ name: "Unknown", value: count["Unknown"] }] : []);
  }, [filteredProjects]);

  // 地图光点 — 只显示筛选后项目所在国家
  const filteredCountries = useMemo(
    () => getUniqueCountries(filteredProjects),
    [filteredProjects],
  );

  const mapDots = useMemo(() => {
    const mapped = filteredCountries.filter((c) => countryCoordinates[c]);
    mapped.sort((a, b) => countryCoordinates[b].x - countryCoordinates[a].x);
    return mapped.map((country, index) => ({
      country,
      x: countryCoordinates[country].x,
      y: countryCoordinates[country].y,
      delay: `${index * 0.2}s`,
    }));
  }, [filteredCountries]);

  // 诊断日志: 打印有光点 / 缺失坐标的国家
  useEffect(() => {
    if (loading) return;
    const withDots = filteredCountries.filter((c) => countryCoordinates[c]);
    const withoutDots = filteredCountries.filter((c) => !countryCoordinates[c]);
    console.log(
      `[Map] %c${withDots.length} countries with dots:%c`,
      "color:#00d4ff;font-weight:bold",
      "color:inherit",
      withDots.join(", ") || "(none)",
    );
    if (withoutDots.length > 0) {
      console.warn(
        `[Map] %c${withoutDots.length} countries MISSING coordinates:%c`,
        "color:#ff9f43;font-weight:bold",
        "color:inherit",
        withoutDots.join(", "),
      );
    } else {
      console.log("[Map] ✅ All countries have coordinates.");
    }
  }, [filteredCountries, loading]);

  const handleDotClick = (country: string) => {
    setSelectedCountry(country);
    console.log(`Dot clicked: ${country} (${projects.filter((p) => p.country.trim() === country).length} projects)`);
  };

  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <>
      <PageMeta title="Business Opportunity Discovery" description="全球 FPSO 项目不锈钢商机挖掘系统" />

      <Header rightContent={
        <>
          <div className="flex flex-shrink-0 items-center gap-2">
            <label htmlFor="country-select" className="hidden text-sm text-fpso-muted lg:inline">
              Region
            </label>
            <select
              id="country-select"
              value={selectedCountry}
              onChange={(e) => {
                setSelectedCountry(e.target.value);
                console.log(`Region changed to: ${e.target.value}`);
              }}
              className="h-9 w-[160px] appearance-none rounded-md border border-fpso-border bg-fpso-card/85 px-3 py-1.5 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="All Countries">All Countries</option>
              {countries.map((country) => {
                const flag = getCountryFlag(projects, country);
                return (
                  <option key={country} value={country}>
                    {flag ? `${flag} ${country}` : country}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <label htmlFor="industry-select" className="hidden text-sm text-fpso-muted lg:inline">
              Industry
            </label>
            <select
              id="industry-select"
              value={selectedIndustry}
              onChange={(e) => {
                setSelectedIndustry(e.target.value);
                console.log(`Industry changed to: ${e.target.value}`);
              }}
              className="h-9 w-[160px] appearance-none rounded-md border border-fpso-border bg-fpso-card/85 px-3 py-1.5 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50"
            >
              {INDUSTRY_OPTIONS.map((opt) => {
                const label =
                  opt === "Desalination" ? `${opt} (海水淡化)` :
                  opt === "General Stainless" ? `${opt} (其他不锈钢)` :
                  opt;
                return <option key={opt} value={opt}>{label}</option>;
              })}
            </select>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <label htmlFor="confidence-select" className="hidden text-sm text-fpso-muted lg:inline">
              Confidence
            </label>
            <select
              id="confidence-select"
              value={selectedConfidence}
              onChange={(e) => setSelectedConfidence(e.target.value)}
              className="h-9 w-[120px] appearance-none rounded-md border border-fpso-border bg-fpso-card/85 px-3 py-1.5 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50"
            >
              <option value="All">All</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <span className="relative inline-flex h-2.5 w-2.5">
              {connectionStatus === "connected" && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fpso-green opacity-75" />
              )}
              <span
                className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                  connectionStatus === "connected" ? "bg-fpso-green live-breath" : "bg-fpso-dim"
                }`}
              />
            </span>
            <span
              className={`text-xs font-medium tracking-wider ${
                connectionStatus === "connected" ? "text-fpso-green" : "text-fpso-dim"
              }`}
            >
              {connectionStatus === "connected" ? "LIVE" : "STALE"}
            </span>
          </div>
        </>
      } />

      <main className="mx-auto w-full max-w-7xl px-6 py-10">
        {/* 页面标题 */}
        <section className="mb-10">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
            全球 FPSO 项目商机挖掘
          </h1>
        </section>

        {/* 全球分布地图 */}
        <section className="mb-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-medium text-fpso-fg">全球分布</h2>
            <span className="text-xs text-fpso-muted">Equirectangular Projection</span>
          </div>

          <div className="map-container relative w-full overflow-hidden rounded-lg border border-fpso-border bg-fpso-card">
            <img
              src="/world-map.png"
              alt="世界地图轮廓"
              className="pointer-events-none absolute inset-0 z-0 h-auto w-full select-none"
              style={{ filter: "brightness(1.3) contrast(1.1)" }}
            />
            {loading ? (
              <div className="flex h-64 items-center justify-center">
                <span className="text-sm text-fpso-muted">Loading map data…</span>
              </div>
            ) : mapDots.length === 0 ? (
              <div className="flex h-64 items-center justify-center">
                <span className="text-sm text-fpso-muted">No project locations found.</span>
              </div>
            ) : (
              mapDots.map((dot) => (
                <button
                  key={dot.country}
                  type="button"
                  onClick={() => handleDotClick(dot.country)}
                  className="map-pulse absolute z-10 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border border-fpso-blue bg-fpso-blue shadow-[0_0_6px_rgba(0,212,255,0.6)] outline-none hover:scale-125 focus:ring-2 focus:ring-fpso-blue/50"
                  style={{
                    left: `${dot.x}%`,
                    top: `${dot.y}%`,
                    animationDelay: dot.delay,
                  }}
                  aria-label={`${dot.country} 项目`}
                />
              ))
            )}
          </div>

          {/* 统计数据 */}
          <div className="mt-6 grid grid-cols-3 gap-4">
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Total</div>
              <div className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-fg">
                {filteredStats.total}
              </div>
            </div>
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Active</div>
              <div className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-blue">
                {filteredStats.active}
              </div>
            </div>
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Planned</div>
              <div className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-orange">
                {filteredStats.planned}
              </div>
            </div>
          </div>
        </section>

        {/* 图表区域 */}
        <section className="mb-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* 国家分布饼图 */}
          <div className="rounded-lg border border-fpso-border bg-fpso-card p-5">
            <h3 className="mb-4 text-sm font-medium text-fpso-fg">Country Distribution</h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={countryChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="value"
                    stroke="transparent"
                  >
                    {countryChartData.map((_, i) => (
                      <Cell
                        key={i}
                        fill={[
                          "#00d4ff", "#ff9f43", "#10b981", "#a78bfa",
                          "#f472b6", "#fbbf24", "#60a5fa", "#34d399",
                        ][i % 8]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "#131a2e",
                      border: "1px solid #1e2844",
                      borderRadius: "8px",
                      fontSize: "13px",
                      color: "#f8fafc",
                    }}
                    formatter={(value: number) => [`${value} projects`, ""]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* 简易图例 */}
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {countryChartData.slice(0, 8).map((d, i) => (
                <span key={d.name} className="inline-flex items-center gap-1.5 text-xs text-fpso-muted">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{
                      background: [
                        "#00d4ff", "#ff9f43", "#10b981", "#a78bfa",
                        "#f472b6", "#fbbf24", "#60a5fa", "#34d399",
                      ][i % 8],
                    }}
                  />
                  {d.name}
                </span>
              ))}
            </div>
          </div>

          {/* 状态分布柱状图 */}
          <div className="rounded-lg border border-fpso-border bg-fpso-card p-5">
            <h3 className="mb-4 text-sm font-medium text-fpso-fg">Status Breakdown</h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusChartData} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#00d4ff" stopOpacity={0.2} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#94a3b8", fontSize: 12 }}
                    axisLine={{ stroke: "#1e2844" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "#94a3b8", fontSize: 12 }}
                    axisLine={{ stroke: "#1e2844" }}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#131a2e",
                      border: "1px solid #1e2844",
                      borderRadius: "8px",
                      fontSize: "13px",
                      color: "#f8fafc",
                    }}
                    formatter={(value: number) => [`${value} projects`, ""]}
                    cursor={{ fill: "rgba(0,212,255,0.08)" }}
                  />
                  <Bar dataKey="value" fill="url(#barGradient)" radius={[4, 4, 0, 0]} maxBarSize={64} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        {/* 项目列表 */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-medium text-fpso-fg">
              项目列表
              {selectedCountry !== "All Countries" && ` — ${selectedCountry}`}
              {selectedIndustry !== "All Industries" && ` — ${selectedIndustry}`}
            </h2>
            <span className="text-xs text-fpso-muted">
              {loading ? "Loading…" : `${filteredProjects.length} records`}
            </span>
          </div>

          <div className="rounded-lg border border-fpso-border bg-fpso-card">
            {loading ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">Loading projects…</div>
            ) : filteredProjects.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">
                No projects found for the selected industry and country.
              </div>
            ) : (
              filteredProjects.map((project) => (
                <div
                  key={project.name}
                  onClick={() => setSelectedProject(project)}
                  className="project-row cursor-pointer border-b border-fpso-border px-5 py-4 last:border-b-0 transition-colors hover:bg-fpso-blue/5"
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-fpso-fg">{project.name}</h3>
                        <span className="inline-flex items-center gap-1 rounded bg-fpso-bg px-2 py-0.5 text-xs text-fpso-muted">
                          {project.flag && <span>{project.flag}</span>}
                          <span>{project.country}</span>
                        </span>
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded bg-fpso-blue/10 px-1.5 py-0.5 text-xs font-medium text-fpso-blue ${project.stainlessSteel ? "" : "hidden"}`}
                        >
                          {project.stainlessSteel}
                        </span>
                        <span
                          className={`rounded bg-fpso-orange/10 px-1.5 py-0.5 text-xs font-medium text-fpso-orange ${project.application ? "" : "hidden"}`}
                        >
                          {project.application}
                        </span>
                        {project.procurementChain && (
                          <span className="rounded bg-fpso-green/10 px-1.5 py-0.5 text-xs font-medium text-fpso-green">
                            采购链: {project.procurementChain}
                          </span>
                        )}
                      </div>

                      <div className="mt-2 flex min-w-0 items-center gap-2">
                        <span className={`h-2 w-2 flex-shrink-0 rounded-full ${statusDotClass(project.status)}`} />
                        <span className={`text-xs ${statusColorClass(project.status)}`}>{project.status}</span>
                        {project.confidence && (
                          <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${confidenceBadgeClass(project.confidence)}`}>
                            {project.confidence}
                          </span>
                        )}
                      </div>

                      <p className="mt-2 truncate text-xs text-fpso-muted">{project.summary}</p>
                    </div>

                    <div className="flex flex-col items-start gap-1 md:items-end md:pl-4">
                      <a
                        href={project.source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="external-link inline-flex items-center gap-1 text-xs text-fpso-blue hover:text-fpso-blue/80"
                      >
                        <span>{project.source.name}</span>
                        <span className="text-[0.8em] leading-none">↗</span>
                      </a>
                      <span className="text-[10px] text-fpso-dim">{project.source.date}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </main>

      {/* 页脚 */}
      <footer className="mt-auto border-t border-fpso-border bg-fpso-bg">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-6 py-5 md:flex-row">
          <span className="text-xs text-fpso-dim">
            Data aggregated from public sources. For internal analysis only.
          </span>
          <span className="text-xs text-fpso-dim">Last updated: {todayStr}</span>
        </div>
      </footer>

      {/* 项目详情模态框 */}
      {selectedProject && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedProject(null)}
        >
          {/* 遮罩层 */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

          {/* 模态框本体 */}
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative z-10 w-full max-w-lg rounded-xl border border-fpso-border bg-fpso-card shadow-2xl animate-fade-in"
          >
            {/* 顶部栏 */}
            <div className="flex items-center justify-between border-b border-fpso-border px-6 py-4">
              <h2 className="text-base font-semibold text-fpso-fg">Project Detail</h2>
              <button
                onClick={() => setSelectedProject(null)}
                className="rounded-md p-1.5 text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg"
                aria-label="Close"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* 内容区 */}
            <div className="space-y-5 px-6 py-5">
              {/* 项目名称 */}
              <h3 className="text-xl font-bold text-fpso-fg">{selectedProject.name}</h3>

              {/* 国家与状态 */}
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1.5 rounded-md bg-fpso-bg px-3 py-1 text-sm text-fpso-fg">
                  {selectedProject.flag && <span>{selectedProject.flag}</span>}
                  <span>{selectedProject.country}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-md bg-fpso-bg px-3 py-1 text-sm">
                  <span className={`h-2 w-2 rounded-full ${statusDotClass(selectedProject.status)}`} style={{ boxShadow: `0 0 6px currentColor` }} />
                  <span className={statusColorClass(selectedProject.status)}>{selectedProject.status || "Unknown"}</span>
                </span>
                {selectedProject.confidence && (
                  <span className={`inline-flex items-center gap-1 rounded-md px-3 py-1 text-sm ${confidenceBadgeClass(selectedProject.confidence)}`}>
                    {selectedProject.confidence}
                  </span>
                )}
              </div>

              {/* 完整摘要 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Summary</h4>
                <p className="text-sm leading-relaxed text-fpso-fg">
                  {selectedProject.summary || "No summary available."}
                </p>
              </div>

              {/* 不锈钢牌号 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Supply Chain Material Matching</h4>
                <p className="text-sm text-fpso-fg">
                  {selectedProject.stainlessSteel ? (
                    <span className="rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-medium text-fpso-blue">
                      {selectedProject.stainlessSteel}
                    </span>
                  ) : "—"}
                </p>
              </div>

              {/* 应用场景 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Application Scenario</h4>
                <p className="text-sm text-fpso-fg">
                  {selectedProject.application ? (
                    <span className="rounded bg-fpso-orange/10 px-2 py-0.5 text-xs font-medium text-fpso-orange">
                      {selectedProject.application}
                    </span>
                  ) : "—"}
                </p>
              </div>

              {/* 采购链 */}
              {selectedProject.procurementChain && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Procurement Chain</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedProject.procurementChain.split(", ").map((entity) => (
                      <span key={entity} className="rounded bg-fpso-green/10 px-2 py-0.5 text-xs font-medium text-fpso-green">
                        {entity}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 来源链接 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Source</h4>
                {selectedProject.source.url ? (
                  <a
                    href={selectedProject.source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-fpso-blue underline-offset-2 hover:underline"
                  >
                    {selectedProject.source.name || selectedProject.source.url}
                    <span className="text-xs">↗</span>
                  </a>
                ) : (
                  <span className="text-sm text-fpso-dim">—</span>
                )}
              </div>

              {/* 抓取日期 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Fetch Date</h4>
                <p className="text-sm text-fpso-dim font-mono text-xs">
                  {selectedProject.source.date || "—"}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
