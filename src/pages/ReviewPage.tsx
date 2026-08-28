/**
 * Review Page — 个人工作区 (Personal Workspace)
 * 浅色数据终端风格。
 *
 * 所有项目直接来自 projects 表，支持关注/忽略标记（localStorage），
 * 不再显示 Accept/Reject/Promote 按钮 — 数据已自动入库。
 */

import { useEffect, useMemo, useState } from "react";
import Header from "@/components/common/Header";
import { ThemeSelect } from "@/components/common/ThemeSelect";
import PageMeta from "@/components/common/PageMeta";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES, countryToFlagEmoji } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { phaseBgClass, phaseFromRow } from "@/lib/project_phase";

/* ------------------------------------------------------------------ */
/*  types                                                              */
/* ------------------------------------------------------------------ */

type BookmarkFilter = "all" | "bookmarked" | "unmarked";

/* ------------------------------------------------------------------ */
/*  localStorage bookmark helpers                                      */
/* ------------------------------------------------------------------ */

const BOOKMARK_KEY = "review_bookmarks";

function loadBookmarks(): Set<string> {
  try {
    const raw = localStorage.getItem(BOOKMARK_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveBookmarks(bookmarks: Set<string>) {
  localStorage.setItem(BOOKMARK_KEY, JSON.stringify([...bookmarks]));
}

/* ------------------------------------------------------------------ */
/*  helpers                                                             */
/* ------------------------------------------------------------------ */

function truncate(text: string, max: number) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function confidenceBgClass(confidence: string): string {
  switch (confidence) {
    case "high":   return "bg-fpso-green/15 text-fpso-green";
    case "medium": return "bg-fpso-orange/15 text-fpso-orange";
    case "low":    return "bg-fpso-muted/15 text-fpso-muted";
    default:       return "bg-fpso-muted/15 text-fpso-muted";
  }
}

function formatDate(d: string | null | undefined) {
  if (!d) return "—";
  return d.slice(0, 10);
}

/** Apply country name alias with case-insensitive fallback. */
function normalizeCountry(raw: string): string {
  if (!raw) return "Unknown";
  const trimmed = raw.trim();
  return COUNTRY_ALIASES[trimmed] ?? COUNTRY_ALIASES[trimmed.toLowerCase()] ?? trimmed;
}

function toNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

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
    phase:          phaseFromRow(row),
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
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    recommendationJson: toStr(row.recommendation_json),
  };
}

/* ------------------------------------------------------------------ */
/*  main page                                                          */
/* ------------------------------------------------------------------ */

export default function ReviewPage() {
  /* ---- state ---- */
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [bookmarks, setBookmarks] = useState<Set<string>>(loadBookmarks);
  const { version, status: connectionStatus } = useProjectRealtime();

  // filters
  const [bookmarkFilter, setBookmarkFilter] = useState<BookmarkFilter>("all");
  const [filterCountry, setFilterCountry] = useState("all");
  const [filterSource, setFilterSource] = useState("all");
  const [searchName, setSearchName] = useState("");

  /* ---- fetch projects ---- */
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
        console.error("[Workspace] Fetch error:", error.message);
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

  /* ---- derive filter options ---- */
  const countries = useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) if (p.country) set.add(p.country.trim());
    return Array.from(set).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
  }, [projects]);

  const sources = useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) if (p.source.name) set.add(p.source.name);
    return Array.from(set).sort();
  }, [projects]);

  /* ---- stats ---- */
  const stats = useMemo(() => {
    let bookmarked = 0;
    let high = 0, medium = 0, low = 0;
    for (const p of projects) {
      if (bookmarks.has(p.name)) bookmarked++;
      const c = p.confidence ?? "medium";
      if (c === "high") high++;
      else if (c === "medium") medium++;
      else low++;
    }
    return { total: projects.length, bookmarked, high, medium, low };
  }, [projects, bookmarks]);

  /* ---- filter ---- */
  const filtered = useMemo(() => {
    let list = projects;

    if (bookmarkFilter === "bookmarked") {
      list = list.filter((p) => bookmarks.has(p.name));
    } else if (bookmarkFilter === "unmarked") {
      list = list.filter((p) => !bookmarks.has(p.name));
    }

    if (filterCountry !== "all") {
      list = list.filter((p) => p.country.trim() === filterCountry);
    }
    if (filterSource !== "all") {
      list = list.filter((p) => p.source.name === filterSource);
    }
    if (searchName.trim()) {
      const q = searchName.trim().toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }

    return list;
  }, [projects, bookmarks, bookmarkFilter, filterCountry, filterSource, searchName]);

  /* ---- actions ---- */
  function toggleBookmark(projectName: string) {
    setBookmarks((prev) => {
      const next = new Set(prev);
      if (next.has(projectName)) {
        next.delete(projectName);
      } else {
        next.add(projectName);
      }
      saveBookmarks(next);
      return next;
    });
  }

  /* ---- render ---- */
  return (
    <>
      <PageMeta title="工作区" description="个人工作区 — 关注/忽略项目" />
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
            Personal Workspace
          </h1>
          <p className="mt-1 text-sm text-fpso-muted">
            {filtered.length} of {projects.length} projects shown
            {stats.bookmarked > 0 && ` — ${stats.bookmarked} bookmarked`}
          </p>
        </section>

        {/* bookmark filter tabs */}
        <section className="mb-6 flex flex-wrap items-center gap-2">
          {([
            ["all", "All"],
            ["bookmarked", "Bookmarked"],
            ["unmarked", "Unmarked"],
          ] as const).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setBookmarkFilter(val)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                bookmarkFilter === val
                  ? "bg-fpso-blue/15 text-fpso-blue"
                  : "text-fpso-muted hover:bg-fpso-bg/50 hover:text-fpso-fg"
              }`}
            >
              {label}
              {val === "bookmarked" && stats.bookmarked > 0 && (
                <span className="ml-1.5 text-xs opacity-60">({stats.bookmarked})</span>
              )}
            </button>
          ))}
        </section>

        {/* filters */}
        <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md px-5 py-3 shadow-card hover:shadow-lift transition-shadow duration-300">
          {/* country */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Country</label>
            <ThemeSelect
              value={filterCountry}
              onChange={setFilterCountry}
              className="min-w-[140px]"
              options={[
                { value: "all", label: "All Countries" },
                ...countries.map((c) => ({
                  value: c,
                  label: countryToFlagEmoji(c) ? `${countryToFlagEmoji(c)} ${c}` : c,
                })),
              ]}
            />
          </div>

          {/* source */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Source</label>
            <ThemeSelect
              value={filterSource}
              onChange={setFilterSource}
              className="min-w-[140px]"
              options={[
                { value: "all", label: "All Sources" },
                ...sources.map((s) => ({ value: s, label: s })),
              ]}
            />
          </div>

          {/* name search */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Search</label>
            <input
              type="text"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder="Project name…"
              className="h-8 w-48 rounded-md bg-fpso-bg/70 px-2.5 py-1 text-sm text-fpso-fg outline-none border border-fpso-border focus:ring-2 focus:ring-fpso-blue/50 placeholder:text-fpso-dim"
            />
          </div>
        </section>

        {/* card list */}
        <section className="space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-fpso-blue/30 border-t-fpso-blue" />
            </div>
          ) : projects.length === 0 ? (
            <div className="rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md px-6 py-16 text-center shadow-card">
              <p className="text-fpso-muted text-sm">No data in projects table.</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md px-6 py-16 text-center shadow-card text-fpso-muted">
              No projects match the current filters ({projects.length} total).
            </div>
          ) : (
            filtered.map((p) => {
              const isBookmarked = bookmarks.has(p.name);
              return (
                <div
                  key={p.name}
                  className="rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md p-5 shadow-card hover:shadow-lift transition-shadow duration-300 hover:border-fpso-blue/30"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    {/* info */}
                    <div className="flex-1 min-w-0 space-y-2">
                      {/* header row */}
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-fpso-fg">
                          {p.name}
                        </h3>
                        <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${phaseBgClass(p.phase)}`}>
                          {p.phase ?? "Unknown"}
                        </span>
                        {p.confidence && (
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${confidenceBgClass(p.confidence)}`}>
                            {p.confidence}
                          </span>
                        )}
                      </div>

                      {/* country + date */}
                      <div className="flex flex-wrap items-center gap-3 text-xs text-fpso-muted">
                        {p.country && <span>{p.flag} {p.country}</span>}
                        {p.source.date && <span>Updated: {formatDate(p.source.date)}</span>}
                        {p.source.name && (
                          <span>
                            Source:{" "}
                            {p.source.url ? (
                              <a
                                href={p.source.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-fpso-blue underline-offset-2 hover:underline"
                              >
                                {p.source.name}
                              </a>
                            ) : (
                              p.source.name
                            )}
                          </span>
                        )}
                      </div>

                      {/* summary */}
                      {p.summary && (
                        <p className="text-sm text-fpso-fg leading-relaxed">
                          {truncate(p.summary, 160)}
                        </p>
                      )}

                      {/* stainless steel + application tags */}
                      <div className="flex flex-wrap items-center gap-2">
                        {p.stainlessSteel && (
                          <span className="rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-medium text-fpso-blue">
                            {p.stainlessSteel}
                          </span>
                        )}
                        {p.application && (
                          <span className="rounded bg-fpso-orange/10 px-2 py-0.5 text-xs font-medium text-fpso-orange">
                            {p.application}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* bookmark toggle */}
                    <div className="flex items-center gap-2 lg:flex-shrink-0">
                      <button
                        onClick={() => toggleBookmark(p.name)}
                        className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                          isBookmarked
                            ? "bg-fpso-green/15 text-fpso-green hover:bg-fpso-green/25 hover:shadow-[0_0_12px_rgba(16,185,129,0.3)]"
                            : "bg-fpso-muted/10 text-fpso-muted hover:bg-fpso-muted/20 hover:text-fpso-fg"
                        }`}
                      >
                        {isBookmarked ? (
                          <>
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                            </svg>
                            Bookmarked
                          </>
                        ) : (
                          <>
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                            </svg>
                            Bookmark
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </section>
      </main>
    </>
  );
}
