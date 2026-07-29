/**
 * Database Page — 项目数据表格视图
 * 深色数据终端风格，支持筛选、分页、行点击详情
 */

import { useEffect, useMemo, useState } from "react";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";

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

/** Apply country name alias with case-insensitive fallback. */
function normalizeCountry(raw: string): string {
  if (!raw) return "Unknown";
  const trimmed = raw.trim();
  return COUNTRY_ALIASES[trimmed] ?? COUNTRY_ALIASES[trimmed.toLowerCase()] ?? trimmed;
}

function mapRowToProject(row: Record<string, unknown>): Project {
  const rawCountry = String(row.country ?? "").trim();
  const country = normalizeCountry(rawCountry);
  const rawName = String(row.name ?? "");
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
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
  };
}

/* ------------------------------------------------------------------ */
/*  constants                                                          */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS = ["All", "Under Construction", "Delivered", "Planned", "Unknown"];
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
  /* ---- state ---- */
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  // filters
  const [countryFilter, setCountryFilter] = useState("All Countries");
  const [statusFilter, setStatusFilter] = useState("All");
  const [nameSearch, setNameSearch] = useState("");

  // pagination
  const [page, setPage] = useState(1);

  // detail panel
  const [selected, setSelected] = useState<Project | null>(null);
  const { version, status: connectionStatus } = useProjectRealtime();

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

    if (countryFilter !== "All Countries") {
      list = list.filter((p) => p.country.trim() === countryFilter);
    }
    if (statusFilter !== "All") {
      list = list.filter((p) => p.status === statusFilter);
    }
    if (nameSearch.trim()) {
      const q = nameSearch.trim().toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }

    return list;
  }, [projects, countryFilter, statusFilter, nameSearch]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);

  const paged = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, safePage]);

  // reset page when filters change
  useEffect(() => { setPage(1); }, [countryFilter, statusFilter, nameSearch]);

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
        <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-fpso-border bg-fpso-card px-5 py-3">
          {/* country */}
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-fpso-muted">Country</label>
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
        </section>

        {/* table */}
        <section className="overflow-hidden rounded-lg border border-fpso-border bg-fpso-card">
          {loading ? (
            <Spinner />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-fpso-border bg-fpso-bg/50 text-left text-xs font-medium uppercase tracking-wider text-fpso-muted">
                    <th className="px-4 py-3">Project</th>
                    <th className="px-4 py-3">Country</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Summary</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-16 text-center text-fpso-muted">
                        No projects match the current filters.
                      </td>
                    </tr>
                  ) : (
                    paged.map((p) => (
                      <tr
                        key={p.name}
                        onClick={() => setSelected(p)}
                        className="border-b border-fpso-border/50 transition-colors hover:bg-fpso-blue/5 cursor-pointer"
                      >
                        <td className="px-4 py-2.5 font-medium text-fpso-fg max-w-[220px] truncate">
                          {p.name}
                        </td>
                        <td className="px-4 py-2.5 text-fpso-muted">
                          {p.flag} {p.country}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBgClass(p.status)}`}>
                            {p.status || "Unknown"}
                          </span>
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
            <div className="flex items-center justify-between border-t border-fpso-border px-4 py-3">
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
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm transition-opacity"
          onClick={() => setSelected(null)}
        />
      )}

      {/* detail panel (slide-in from right) */}
      <aside
        className={`fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto border-l border-fpso-border bg-fpso-card shadow-2xl transition-transform duration-300 ${
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
            </div>

            {/* summary */}
            <section className="mb-6">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Summary</h4>
              <p className="text-sm leading-relaxed text-fpso-fg">
                {selected.summary || "No summary available."}
              </p>
            </section>

            {/* stainless steel grade */}
            <section className="mb-6">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Stainless Steel Grade</h4>
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
    </>
  );
}
