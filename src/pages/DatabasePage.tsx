/**
 * Database Page — 项目数据表格视图
 * 深色数据终端风格，支持筛选、分页、行点击详情
 */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { useTimelineEventCounts } from "@/hooks/useTimelineEventCounts";
import { filterMatureProjects, hasTimelineData } from "@/lib/project_maturity";
import { hasAnySpecs, parseRecommendation, parseCorrosiveMedia, getCorrosiveMediaTags, getCorrosiveMediaDetails } from "@/lib/material_matcher";
import { scoreOpportunity, scoreBadgeClass } from "@/lib/opportunity_scorer";
import BattleCardWrapper from "@/components/dashboard/BattleCard";
import FollowUpStatus from "@/components/dashboard/FollowUpStatus";
import { useSubscription } from "@/hooks/useSubscription";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

/* ------------------------------------------------------------------ */
/*  shared helpers (same semantics as DashboardPage)                   */
/* ------------------------------------------------------------------ */

function getUniqueCountries(projects: Project[]): string[] {
  const set = new Set<string>();
  for (const p of projects) set.add(p.country.trim());
  return Array.from(set).sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" }),
  );
}

function getCountryFlag(projects: Project[], country: string): string {
  const found = projects.find((p) => p.country.trim() === country.trim() && p.flag);
  return found?.flag ?? "";
}

function statusColorClass(status: string): string {
  switch (status) {
    case "Under Construction": return "text-fpso-blue";
    case "Delivered":        return "text-fpso-green";
    case "Planned":          return "text-fpso-orange";
    default:                 return "text-fpso-muted";
  }
}

function statusBgClass(status: string): string {
  switch (status) {
    case "Under Construction": return "bg-fpso-blue/15 text-fpso-blue";
    case "Delivered":        return "bg-fpso-green/15 text-fpso-green";
    case "Planned":          return "bg-fpso-orange/15 text-fpso-orange";
    default:                 return "bg-fpso-muted/15 text-fpso-muted";
  }
}

function confidenceBgClass(confidence: string): string {
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

/** Parse a nullable int column from Supabase row. */
function toNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Parse a nullable text column from Supabase row. */
function toStr(v: unknown): string | null {
  if (v == null || v === "") return null;
  const s = String(v).trim();
  return s || null;
}

function mapRowToProject(row: Record<string, unknown>): Project {
  const rawCountry = String(row.country ?? "").trim();
  const country = normalizeCountry(rawCountry);
  const rawName = String(row.name ?? "");
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
  const confidence = String(row.confidence ?? "medium") as "high" | "medium" | "low";
  return {
    name,
    country,
    flag:           String(row.flag ?? ""),
    status:         String(row.status ?? ""),
    summary:        String(row.summary ?? ""),
    source: {
      name: String(row.source_name ?? ""),
      url:  String(row.source_url ?? ""),
      date: String(row.source_date ?? ""),
    },
    stainlessSteel: String(row.stainless_steel ?? ""),
    application:    String(row.application ?? ""),
    confidence,
    procurementChain: String(row.procurement_chain ?? ""),
    // Technical specs
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    recommendationJson: toStr(row.recommendation_json),
    corrosiveMedia: parseCorrosiveMedia(row.corrosive_media),
  };
}

/* ------------------------------------------------------------------ */
/*  constants                                                          */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS = ["Active Projects", "All", "Under Construction", "Delivered", "Planned", "Unknown"];
const INDUSTRY_OPTIONS = [
  "All Industries",
  "FPSO",
  "Desalination",
  "LNG",
  "General Stainless",
] as const;
const PAGE_SIZE = 20;
const MAX_VISIBLE_PAGES = 5;

/* ------------------------------------------------------------------ */
/*  sub-components                                                     */
/* ------------------------------------------------------------------ */

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-fpso-blue/30 border-t-fpso-blue" />
    </div>
  );
}

/** Build page-number array with ellipsis for large page counts. */
function buildPages(current: number, total: number): (number | "...")[] {
  if (total <= MAX_VISIBLE_PAGES + 2) {
    // show all
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | "...")[] = [];
  pages.push(1);

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  if (start > 2) pages.push("...");
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < total - 1) pages.push("...");

  pages.push(total);
  return pages;
}

/* ------------------------------------------------------------------ */
/*  main page                                                          */
/* ------------------------------------------------------------------ */

export default function DatabasePage() {
  const [searchParams] = useSearchParams();

  /* ---- state ---- */
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  // filters — industry seeded from ?industry= URL param
  const [industryFilter, setIndustryFilter] = useState(() => {
    const fromUrl = searchParams.get("industry");
    if (fromUrl && (INDUSTRY_OPTIONS as readonly string[]).includes(fromUrl)) {
      return fromUrl;
    }
    return "All Industries";
  });
  const [countryFilter, setCountryFilter] = useState("All Countries");
  const [statusFilter, setStatusFilter] = useState("Active Projects");
  const [confidenceFilter, setConfidenceFilter] = useState("High & Medium");
  const [nameSearch, setNameSearch] = useState("");
  const [showAllProjects, setShowAllProjects] = useState(false);

  // pagination
  const [page, setPage] = useState(1);

  // sort
  const [sortField, setSortField] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // detail panel
  const [selected, setSelected] = useState<Project | null>(null);
  const [battleCardProject, setBattleCardProject] = useState<Project | null>(null);

  // subscription (follow/unfollow)
  const { isFollowing, toggleFollowProject, isAuthenticated } = useSubscription();
  const { isGuest } = useAuth();
  const { version, status: connectionStatus } = useProjectRealtime();
  const timelineEventCounts = useTimelineEventCounts(version);

  /* ---- fetch ---- */
  useEffect(() => {
    if (!supabase) {
      setProjects(sampleProjects);
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchProjects() {
      const { data, error } = await supabase!.from("projects").select("*");

      if (error) {
        console.error("Database fetch error:", error.message);
        if (!cancelled) setProjects(sampleProjects);
        return;
      }

      const mapped = (data ?? []).map(mapRowToProject);
      const seen = new Set<string>();
      const unique = mapped.filter((p) => {
        const k = p.name.trim();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });

      if (!cancelled) {
        setProjects(unique.length > 0 ? unique : sampleProjects);
      }
    }

    fetchProjects().finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [version]);

  /* ---- derive ---- */
  const countries = useMemo(() => getUniqueCountries(projects), [projects]);

  const filtered = useMemo(() => {
    let list = projects;

    if (industryFilter !== "All Industries") {
      list = list.filter((p) => (p.industry ?? "FPSO") === industryFilter);
    }
    if (countryFilter !== "All Countries") {
      list = list.filter((p) => p.country.trim() === countryFilter);
    }
    if (statusFilter === "Active Projects") {
      list = list.filter((p) => p.status === "Under Construction" || p.status === "Planned");
    } else if (statusFilter !== "All") {
      list = list.filter((p) => p.status === statusFilter);
    }
    if (confidenceFilter === "High & Medium") {
      list = list.filter(
        (p) => (p.confidence ?? "medium") !== "low",
      );
    } else if (confidenceFilter !== "All") {
      list = list.filter(
        (p) => (p.confidence ?? "medium") === confidenceFilter.toLowerCase(),
      );
    }
    if (nameSearch.trim()) {
      const q = nameSearch.trim().toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }

    // Maturity filter: default shows mature opportunities only.
    list = filterMatureProjects(list, timelineEventCounts, showAllProjects);

    // Apply sort
    if (sortField === "score") {
      list = [...list].sort((a, b) => {
        const sa = scoreOpportunity(a).totalScore;
        const sb = scoreOpportunity(b).totalScore;
        return sortDir === "desc" ? sb - sa : sa - sb;
      });
    }

    return list;
  }, [projects, industryFilter, countryFilter, statusFilter, confidenceFilter, nameSearch, sortField, sortDir, timelineEventCounts, showAllProjects]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);

  const paged = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, safePage]);

  // reset page when filters change
  useEffect(() => { setPage(1); }, [industryFilter, countryFilter, statusFilter, confidenceFilter, nameSearch]);

  const pages = buildPages(safePage, totalPages);

  /* ---- truncate ---- */
  function truncate(text: string, max: number) {
    return text.length > max ? text.slice(0, max) + "…" : text;
  }

  /* ---- render ---- */
  return (
    <>
      <PageMeta title="Database — FPSO Projects" description="项目数据库表格视图" />
      <Header rightContent={
        <div className="flex items-center gap-2">
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
      } />

      <main className="mx-auto w-full max-w-7xl px-6 py-8">
        {/* page title */}
        <section className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
            项目数据库
          </h1>
          <p className="mt-1 text-sm text-fpso-muted">
            {filtered.length} of {projects.length} projects
          </p>
        </section>

        {/* filters */}
        <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md px-5 py-3 shadow-xl hover:shadow-2xl transition-shadow duration-300">
          {/* industry */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Industry</label>
            <select
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="h-8 min-w-[150px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50 border border-fpso-border"
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

          {/* region */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Region</label>
            <select
              value={countryFilter}
              onChange={(e) => setCountryFilter(e.target.value)}
              className="h-8 min-w-[140px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50 border border-fpso-border"
            >
              <option value="All Countries">All Countries</option>
              {countries.map((c) => {
                const flag = getCountryFlag(projects, c);
                return (
                  <option key={c} value={c}>
                    {flag ? `${flag} ${c}` : c}
                  </option>
                );
              })}
            </select>
          </div>

          {/* status */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-8 min-w-[160px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50 border border-fpso-border"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* confidence */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Confidence</label>
            <select
              value={confidenceFilter}
              onChange={isGuest ? () => {} : (e) => setConfidenceFilter(e.target.value)}
              disabled={isGuest}
              className="h-8 min-w-[120px] rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50 border border-fpso-border disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="High & Medium">High &amp; Medium</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
              <option value="All">All</option>
            </select>
          </div>

          {/* name search */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Search</label>
            <input
              type="text"
              value={nameSearch}
              onChange={(e) => setNameSearch(e.target.value)}
              placeholder="Project name…"
              className="h-8 w-48 rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50 border border-fpso-border placeholder:text-fpso-dim"
            />
          </div>

          {/* show-all toggle */}
          <div className="ml-auto flex items-center gap-2">
            <label
              htmlFor="show-all-toggle"
              className="text-xs font-medium text-fpso-muted cursor-pointer"
            >
              显示全部项目（含待挖掘）
            </label>
            <Switch
              id="show-all-toggle"
              checked={showAllProjects}
              onCheckedChange={setShowAllProjects}
            />
          </div>
        </section>

        {/* table */}
        <section className="overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300">
          {loading ? (
            <Spinner />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5 bg-fpso-bg/40 backdrop-blur-md text-left text-xs font-medium uppercase tracking-wider text-fpso-muted">
                    <th className="px-4 py-3">Project</th>
                    <th className="px-4 py-3">Country</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Corrosive</th>
                    <th className="px-4 py-3">Confidence</th>
                    <th
                      className="px-4 py-3 cursor-pointer hover:text-fpso-blue transition-colors select-none"
                      onClick={() => {
                        if (sortField === "score") {
                          setSortDir((d) => (d === "desc" ? "asc" : "desc"));
                        } else {
                          setSortField("score");
                          setSortDir("desc");
                        }
                        setPage(1);
                      }}
                    >
                      Score{sortField === "score" ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
                    </th>
                    <th className="px-4 py-3">Procurement</th>
                    <th className="px-4 py-3">Summary</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="px-4 py-16 text-center text-fpso-muted">
                        No projects match the current filters.
                      </td>
                    </tr>
                  ) : (
                    paged.map((p) => (
                      <tr
                        key={p.name}
                        onClick={() => setSelected(p)}
                        className="border-b border-white/5 transition-colors hover:bg-fpso-blue/5 cursor-pointer"
                      >
                        <td className="px-4 py-2.5 font-medium text-fpso-fg max-w-[220px] truncate">
                          {p.name}
                          {showAllProjects && !hasTimelineData(p, timelineEventCounts) && (
                            <span
                              className="ml-2 inline-block rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400 ring-1 ring-amber-400/20"
                              title="暂无足够商机数据，已加入待挖掘池"
                            >
                              待挖掘
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-fpso-muted">
                          {p.flag} {p.country}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBgClass(p.status)}`}>
                            {p.status || "Unknown"}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          {(() => {
                            const cmTags = getCorrosiveMediaTags(p.corrosiveMedia);
                            if (cmTags.length === 0) return <span className="text-fpso-dim">—</span>;
                            return (
                              <div className="flex flex-wrap items-center gap-0.5">
                                {cmTags.map((tag) => (
                                  <span
                                    key={tag.key}
                                    className={`inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border ${tag.className}`}
                                  >
                                    {tag.label}
                                  </span>
                                ))}
                              </div>
                            );
                          })()}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${confidenceBgClass(p.confidence ?? "medium")}`}>
                            {p.confidence ?? "medium"}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          {(() => {
                            const sr = scoreOpportunity(p);
                            return (
                              <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${scoreBadgeClass(sr.grade)}`}>
                                {sr.grade} {sr.totalScore}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="px-4 py-2.5">
                          {p.procurementChain ? (
                            <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium bg-fpso-green/15 text-fpso-green max-w-[200px] truncate" title={p.procurementChain}>
                              采购链: {p.procurementChain}
                            </span>
                          ) : (
                            <span className="text-fpso-dim">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-fpso-muted max-w-[280px] truncate">
                          {truncate(p.summary, 60)}
                        </td>
                        <td className="px-4 py-2.5">
                          {p.source.url ? (
                            <a
                              href={p.source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-fpso-blue underline-offset-2 hover:underline"
                            >
                              {p.source.name || "Link"}
                            </a>
                          ) : (
                            <span className="text-fpso-dim">{p.source.name || "—"}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-fpso-dim font-mono text-xs">
                          {p.source.date || "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* pagination */}
          {!loading && totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-white/5 px-4 py-3">
              <span className="text-xs text-fpso-dim">
                Page {safePage} of {totalPages}
              </span>
              <div className="flex items-center gap-1">
                <button
                  disabled={safePage <= 1}
                  onClick={() => setPage((pg) => Math.max(1, pg - 1))}
                  className="rounded-md px-3 py-1 text-xs font-medium text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Prev
                </button>

                {pages.map((p, i) =>
                  p === "..." ? (
                    <span key={`ellip-${i}`} className="px-1 text-xs text-fpso-dim">…</span>
                  ) : (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                        p === safePage
                          ? "bg-fpso-blue/15 text-fpso-blue"
                          : "text-fpso-muted hover:bg-fpso-bg/50 hover:text-fpso-fg"
                      }`}
                    >
                      {p}
                    </button>
                  ),
                )}

                <button
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((pg) => Math.min(totalPages, pg + 1))}
                  className="rounded-md px-3 py-1 text-xs font-medium text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* detail panel overlay */}
      {selected && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md transition-opacity"
          onClick={() => setSelected(null)}
        />
      )}

      {/* detail panel (slide-in from right) */}
      <aside
        className={`fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto border-l border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-2xl transition-transform duration-300 ${
          selected ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {selected && (
          <div className="px-6 py-6">
            {/* close button */}
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-fpso-fg">Project Detail</h2>
              <button
                onClick={() => setSelected(null)}
                className="rounded-md p-1.5 text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg"
                aria-label="Close detail panel"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* project name */}
            <h3 className="mb-1 text-xl font-bold text-fpso-fg">{selected.name}</h3>
            <div className="mb-4 flex items-center gap-3 text-sm">
              <span className="text-fpso-muted">{selected.flag} {selected.country}</span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBgClass(selected.status)}`}>
                {selected.status || "Unknown"}
              </span>
              {selected.confidence && (
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${confidenceBgClass(selected.confidence)}`}>
                  {selected.confidence}
                </span>
              )}
            </div>

            {/* follow / unfollow button — hidden for guests */}
            {isAuthenticated && !isGuest && (
              <div className="mb-4">
                <Button
                  variant={isFollowing(selected.name) ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => toggleFollowProject(selected.name)}
                  className={
                    isFollowing(selected.name)
                      ? 'bg-fpso-blue hover:bg-fpso-blue/80 text-white text-xs'
                      : 'border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-xs'
                  }
                >
                  {isFollowing(selected.name) ? '★ Following' : '☆ Follow'}
                </Button>
              </div>
            )}

            {/* Follow-up Status (S7) — hidden for guests */}
            {!isGuest && (
              <section className="mb-6">
                <FollowUpStatus
                  projectId={selected.name}
                  projectName={selected.name}
                />
              </section>
            )}

            {/* summary */}
            <section className="mb-6">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Summary</h4>
              <p className="text-sm leading-relaxed text-fpso-fg">
                {selected.summary || "No summary available."}
              </p>
            </section>

            {/* stainless steel grade */}
            <section className="mb-6">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Supply Chain Material Matching</h4>
              <p className="text-sm text-fpso-fg">
                {selected.stainlessSteel || "—"}
              </p>
            </section>

            {/* application scenario */}
            <section className="mb-6">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Application Scenario</h4>
              <p className="text-sm text-fpso-fg">
                {selected.application || "—"}
              </p>
            </section>

            {/* procurement chain */}
            {selected.procurementChain && (
              <section className="mb-6">
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Procurement Chain</h4>
                <div className="flex flex-wrap gap-1.5">
                  {selected.procurementChain.split(", ").map((entity) => (
                    <span key={entity} className="rounded-md bg-fpso-green/15 px-2.5 py-1 text-xs font-medium text-fpso-green">
                      {entity}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* Technical Specs & Material Matching */}
            {(() => {
              const specs = {
                waterDepthM: selected.waterDepthM,
                oilCapacityBpd: selected.oilCapacityBpd,
                gasCapacityMmcmd: selected.gasCapacityMmcmd,
                hullType: selected.hullType,
                fieldName: selected.fieldName,
                operatorName: selected.operatorName,
                basin: selected.basin,
              };
              const rec = parseRecommendation(selected.recommendationJson);
              const showSpecs = hasAnySpecs(specs);
              const showRec = rec !== null;
              if (!showSpecs && !showRec) return null;
              return (
                <section className="mb-6">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
                    Technical Specs &amp; Material Matching
                  </h4>
                  {/* Technical parameters table */}
                  {showSpecs && (
                    <div className="mb-3 overflow-hidden rounded-md border border-white/5">
                      <table className="w-full text-xs">
                        <tbody>
                          {specs.waterDepthM != null && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Water Depth</td>
                              <td className="px-3 py-1.5 text-fpso-fg font-mono">{specs.waterDepthM.toLocaleString()} m</td>
                            </tr>
                          )}
                          {specs.oilCapacityBpd != null && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Oil Capacity</td>
                              <td className="px-3 py-1.5 text-fpso-fg font-mono">{specs.oilCapacityBpd.toLocaleString()} bpd</td>
                            </tr>
                          )}
                          {specs.gasCapacityMmcmd != null && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Gas Capacity</td>
                              <td className="px-3 py-1.5 text-fpso-fg font-mono">{specs.gasCapacityMmcmd.toLocaleString()} MMcmd</td>
                            </tr>
                          )}
                          {specs.hullType && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Hull Type</td>
                              <td className="px-3 py-1.5 text-fpso-fg">{specs.hullType}</td>
                            </tr>
                          )}
                          {specs.fieldName && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Field</td>
                              <td className="px-3 py-1.5 text-fpso-fg">{specs.fieldName}</td>
                            </tr>
                          )}
                          {specs.operatorName && (
                            <tr className="border-b border-white/5">
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Operator</td>
                              <td className="px-3 py-1.5 text-fpso-fg">{specs.operatorName}</td>
                            </tr>
                          )}
                          {specs.basin && (
                            <tr>
                              <td className="px-3 py-1.5 text-fpso-muted font-medium">Basin</td>
                              <td className="px-3 py-1.5 text-fpso-fg">{specs.basin}</td>
                            </tr>
                          )}
                          {/* Corrosive Media */}
                          <tr>
                            <td className="px-3 py-1.5 text-fpso-muted font-medium align-top">Corrosive Media</td>
                            <td className="px-3 py-1.5">
                              {(() => {
                                const cmTags = getCorrosiveMediaTags(selected.corrosiveMedia);
                                const cmDetails = getCorrosiveMediaDetails(selected.corrosiveMedia);
                                if (cmTags.length === 0) {
                                  return <span className="text-fpso-dim text-[11px] italic">No corrosive media data available</span>;
                                }
                                return (
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    {cmTags.map((tag) => (
                                      <span
                                        key={tag.key}
                                        className={`inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border ${tag.className}`}
                                      >
                                        {tag.label}
                                      </span>
                                    ))}
                                    {cmDetails && (
                                      <span className="text-[11px] text-fpso-muted ml-1">{cmDetails}</span>
                                    )}
                                  </div>
                                );
                              })()}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}
                  {/* Material recommendation */}
                  {showRec && (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-fpso-muted">Grades:</span>
                        {rec.grades.map((g) => (
                          <span key={g} className="rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-medium text-fpso-blue">
                            {g}
                          </span>
                        ))}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-fpso-muted">Applications:</span>
                        {rec.applications.map((a) => (
                          <span key={a} className="rounded bg-fpso-orange/10 px-2 py-0.5 text-xs font-medium text-fpso-orange">
                            {a}
                          </span>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-fpso-muted">Confidence:</span>
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                          rec.confidence === "high" ? "bg-fpso-green/15 text-fpso-green" :
                          rec.confidence === "medium" ? "bg-fpso-orange/15 text-fpso-orange" :
                          "bg-fpso-muted/15 text-fpso-muted"
                        }`}>
                          {rec.confidence}
                        </span>
                      </div>
                      {(() => {
                        const hasCorrosiveReasoning = /H₂S|CO₂|sour|NACE|corrosive|H2S|chloride|Cl⁻/i.test(rec.reasoning);
                        if (hasCorrosiveReasoning) {
                          return (
                            <blockquote className="border-l-2 border-fpso-orange/40 pl-3 text-xs leading-relaxed text-fpso-orange/80 italic mt-2">
                              {rec.reasoning}
                            </blockquote>
                          );
                        }
                        return (
                          <p className="text-xs leading-relaxed text-fpso-dim italic">{rec.reasoning}</p>
                        );
                      })()}
                    </div>
                  )}
                </section>
              );
            })()}

            {/* Opportunity Score (S5) */}
            {(() => {
              const scoreResult = scoreOpportunity(selected);
              return (
                <section>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
                    Opportunity Score
                  </h4>
                  <div className="mb-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-bold text-fpso-fg">
                        {scoreResult.totalScore}<span className="text-fpso-dim font-normal">/100</span>
                      </span>
                      <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-bold uppercase ${scoreBadgeClass(scoreResult.grade)}`}>
                        Grade {scoreResult.grade}
                      </span>
                    </div>
                    <div className="h-3 w-full rounded-full bg-fpso-bg overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          scoreResult.grade === "A" ? "bg-fpso-green" :
                          scoreResult.grade === "B" ? "bg-fpso-blue" :
                          scoreResult.grade === "C" ? "bg-fpso-orange" : "bg-fpso-muted"
                        }`}
                        style={{ width: `${scoreResult.totalScore}%` }}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-fpso-muted mb-2">{scoreResult.summary}</p>
                  <p className="text-xs text-fpso-fg mb-3">
                    <span className="font-semibold text-fpso-blue">Action: </span>
                    {scoreResult.recommendedAction}
                  </p>
                  {/* Battle Card button — hidden for guests */}
                  {!isGuest && (
                    <button
                      type="button"
                      onClick={() => setBattleCardProject(selected)}
                      className="mb-3 inline-flex items-center gap-1.5 rounded-md border border-fpso-green/20 bg-fpso-green/5 px-3 py-1.5 text-xs font-medium text-fpso-green hover:bg-fpso-green/10 hover:border-fpso-green/30 transition-colors"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      生成作战卡
                    </button>
                  )}
                  <details className="group mb-2">
                    <summary className="text-xs font-medium text-fpso-blue hover:text-fpso-blue/80 transition-colors cursor-pointer select-none">
                      Show dimension details
                    </summary>
                    <div className="mt-2 space-y-2 pl-2 border-l-2 border-fpso-blue/20">
                      {[
                        { key: "procurement", label: "Procurement Probability" },
                        { key: "factoryMatch", label: "Factory Match" },
                        { key: "reachability", label: "Reachability" },
                        { key: "value", label: "Project Value" },
                        { key: "confidence", label: "Information Confidence" },
                      ].map(({ key, label }) => {
                        const dim = scoreResult.dimensions[key as keyof typeof scoreResult.dimensions];
                        return (
                          <div key={key}>
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-xs text-fpso-muted">{label}</span>
                              <span className="text-xs font-mono font-bold text-fpso-fg">{dim.score}/20</span>
                            </div>
                            <div className="h-1.5 w-full rounded-full bg-fpso-bg overflow-hidden mb-0.5">
                              <div
                                className="h-full rounded-full bg-fpso-blue/60"
                                style={{ width: `${(dim.score / 20) * 100}%` }}
                              />
                            </div>
                            <p className="text-[11px] text-fpso-dim leading-relaxed">{dim.reasoning}</p>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </section>
              );
            })()}

            {/* source */}
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Source</h4>
              {selected.source.url ? (
                <a
                  href={selected.source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-fpso-blue underline-offset-2 hover:underline"
                >
                  {selected.source.name || selected.source.url}
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              ) : (
                <span className="text-sm text-fpso-dim">—</span>
              )}
              {selected.source.date && (
                <p className="mt-1 text-xs text-fpso-dim">Fetched {selected.source.date}</p>
              )}
            </section>
          </div>
        )}
      </aside>

      {/* 作战卡弹窗 */}
      {battleCardProject && (
        <div
          className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[5vh]"
          onClick={() => setBattleCardProject(null)}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative z-10 w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-fade-in"
          >
            <div className="flex justify-end mb-2">
              <button
                onClick={() => setBattleCardProject(null)}
                className="rounded-md p-1.5 text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg"
                aria-label="Close battle card"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <BattleCardWrapper
              project={battleCardProject}
              baseUrl={window.location.origin}
            />
          </div>
        </div>
      )}
    </>
  );
}
