/**
 * ProjectTimelinePage — 全屏项目时间线视图
 * 路由: /project-timeline?project={canonicalId}
 * 从 Dashboard 详情弹窗的 Timeline 标签跳转访问。
 */

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import PageHeader from "@/components/common/PageHeader";
import SidebarShell, { SIDEBAR_EXPANDED, SIDEBAR_COLLAPSED } from "@/components/common/SidebarShell";
import { SourceLinkBadge } from "@/components/common/SourceLinkBadge";
import { supabase, fetchAllRows } from "@/db/supabase";
import { phaseFromRow } from "@/lib/project_phase";
import {
  getAllCanonicalIds,
  getDisplayName,
  getProjectCountry,
  getAliases,
  sortPriorityFirst,
  priorityProjectRank,
} from "@/data/project_aliases";
import type { Project } from "@/data/projects";
import { countryToFlagEmoji, COUNTRY_ALIASES, normalizeIndustry } from "@/data/projects";
import { sortTimelineEvents } from "@/lib/event_types";
import { Search, ChevronDown, ChevronRight, ExternalLink, Anchor, Waves, Gauge } from "lucide-react";

// ---- Types ----

interface TimelineEventFull {
  id: number;
  eventType: string;
  publicationDate: string;
  sourceName: string;
  sourceUrl: string;
  evidenceQuote: string;
  summary: string;
}

interface ProjectOption {
  canonicalId: string;
  displayName: string;
  country: string;
}

// ---- Event type labels ----

const EVENT_TYPE_LABELS: Record<string, string> = {
  "EIA_SUBMITTED": "EIA Submitted",
  "DEVELOPMENT_CONSENT_GRANTED": "Development Consent Granted",
  "REGULATORY_DATA": "Regulatory Filing",
  "FPSO_CONTRACT_AWARDED": "FPSO Contract Awarded",
  "DEVELOPMENT_PLAN_SUBMITTED": "Development Plan Submitted",
  "DEVELOPMENT_PLAN_UPDATED": "Development Plan Updated",
  "PERMIT_GRANTED": "Permit Granted",
  "LICENSE_GRANTED": "License Granted",
  "FIELD_DEVELOPMENT_PLAN": "Field Development Plan",
  "PRODUCTION_START": "Production Start",
  "FIRST_OIL": "First Oil",
  "VENDOR_REGISTRATION_ACTION": "Vendor Registration",
  "PUBLIC_NOTICE": "Public Notice",
  "CONTRACT_ANNOUNCEMENT": "Contract Announcement",
  "ARTICLE_MENTION": "Article Mention",
  "BACKFILL_COUNTRY": "Backfill Entry",
};

function formatEventType(et: string): string {
  return EVENT_TYPE_LABELS[et] ?? et.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---- Event category for filtering ----

type EventCategory = "PRODUCTION" | "CONTRACT" | "EIA" | "REGULATORY" | "OTHER";

/** 单一颜色源：chips 与圆点共用（hex 对齐 fpso token） */
const CATEGORY_OPTIONS: { key: EventCategory; label: string; color: string }[] = [
  { key: "PRODUCTION", label: "投产", color: "#059669" },
  { key: "CONTRACT", label: "合同", color: "#0284c7" },
  { key: "EIA", label: "EIA/计划", color: "#ea580c" },
  { key: "REGULATORY", label: "监管/许可", color: "#db2777" },
  { key: "OTHER", label: "其他", color: "#64748b" },
];

function categorizeEvent(eventType: string): EventCategory {
  const et = eventType.toUpperCase();
  if (/PRODUCTION_START|FIRST_OIL/.test(et)) return "PRODUCTION";
  if (/CONTRACT|AWARDED/.test(et)) return "CONTRACT";
  if (/EIA|DEVELOPMENT_PLAN/.test(et)) return "EIA";
  if (/REGULATORY|PERMIT|LICENSE|GRANTED|CONSENT|PUBLIC_NOTICE/.test(et)) return "REGULATORY";
  return "OTHER";
}

function timelineDotStyle(eventType: string): string {
  const cat = categorizeEvent(eventType);
  return CATEGORY_OPTIONS.find((c) => c.key === cat)?.color ?? "#64748b";
}

// ---- Helpers ----

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
  if (v == null) return null;
  const s = String(v).trim();
  return s === "" ? null : s;
}

function matchesProjectQuery(p: ProjectOption, q: string): boolean {
  return (
    p.displayName.toLowerCase().includes(q) ||
    p.country.toLowerCase().includes(q) ||
    p.canonicalId.toLowerCase().includes(q)
  );
}

// ---- Component ----

export default function ProjectTimelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Project selection
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  // "待挖掘项目" collapsed group — expanded only on explicit click.
  const [minedOpen, setMinedOpen] = useState(false);
  // 左侧栏 — 默认折叠，与商机看板 / 战报中心一致
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  // Timeline
  const [events, setEvents] = useState<TimelineEventFull[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [activeCategories, setActiveCategories] = useState<Set<EventCategory>>(
    new Set(CATEGORY_OPTIONS.map((c) => c.key)),
  );

  // Project info
  const [projectInfo, setProjectInfo] = useState<Project | null>(null);

  // Non-canonical project name (fallback for unmatched projects)
  const [rawProjectName, setRawProjectName] = useState<string>("");

  // Accepted-event counts per canonical id (canonical link + alias name
  // match). Drives default selection and the "暂无时间线" marks.
  const [eventCounts, setEventCounts] = useState<Map<string, number>>(new Map());
  const [countsLoading, setCountsLoading] = useState(true);

  // Build project option list from alias registry
  useEffect(() => {
    const ids = getAllCanonicalIds();
    const list: ProjectOption[] = ids.map((id) => ({
      canonicalId: id,
      displayName: getDisplayName(id),
      country: getProjectCountry(id),
    }));
    list.sort((a, b) => a.displayName.localeCompare(b.displayName));
    setProjects(list);
  }, []);

  // Fetch accepted-event coverage for the whole registry once, so the
  // default selection can pick a project that actually has timeline data.
  useEffect(() => {
    let cancelled = false;

    async function fetchCounts() {
      const { data, error } = await fetchAllRows(
        "candidate_events",
        "id, canonical_project_id, project_name_raw, review_status",
      );

      const map = new Map<string, number>();
      if (!cancelled && !error && data) {
        // Timeline shows only accepted events — rejected rows are noise and
        // pending rows are unreviewed (e.g. 359 duplicate Tartaruga Verde
        // rows still awaiting review).
        const accepted = data.filter(
          (r) => String(r.review_status ?? "").toLowerCase() === "accepted",
        );
        const ids = getAllCanonicalIds();
        const aliasLookup = ids.map((id) => ({
          id,
          aliases: [getDisplayName(id), ...getAliases(id)]
            .map((a) => a.toLowerCase())
            .filter((a) => a.length >= 4),
        }));
        for (const { id, aliases } of aliasLookup) {
          const cnt = accepted.filter((r) => {
            if (String(r.canonical_project_id ?? "").trim() === id) return true;
            const raw = String(r.project_name_raw ?? "").toLowerCase();
            return aliases.some((al) => raw.includes(al));
          }).length;
          if (cnt > 0) map.set(id, cnt);
        }
      }
      if (!cancelled) {
        setEventCounts(map);
        setCountsLoading(false);
      }
    }

    fetchCounts();

    return () => { cancelled = true; };
  }, []);

  // Initial selection: URL param wins; otherwise pick the first project
  // in selector order (pinned first, then alphabetical) that has accepted
  // timeline events, so the first screen is never blank.
  const initialSelectionDone = useRef(false);
  useEffect(() => {
    if (projects.length === 0 || countsLoading || initialSelectionDone.current) return;

    const urlProject = searchParams.get("project");
    const urlProjectName = searchParams.get("projectName");

    if (urlProject && projects.some((p) => p.canonicalId === urlProject)) {
      setSelectedId(urlProject);
    } else if (urlProjectName) {
      // Fallback: project not in alias registry — use raw name
      setRawProjectName(urlProjectName);
      setSelectedId(""); // will trigger fallback query
    } else {
      const withEvents = projects.filter(
        (p) => (eventCounts.get(p.canonicalId) ?? 0) > 0,
      );
      const firstWithEvents =
        sortPriorityFirst(withEvents, (p) => priorityProjectRank(p.canonicalId))[0] ??
        projects[0];
      setSelectedId(firstWithEvents.canonicalId);
      setSearchParams({ project: firstWithEvents.canonicalId }, { replace: true });
    }
    initialSelectionDone.current = true;
  }, [projects, eventCounts, countsLoading]);

  // Determine the effective query target
  const queryTarget = selectedId || rawProjectName;
  const isCanonical = Boolean(selectedId);

  // Fetch timeline events when project changes
  useEffect(() => {
    if (!queryTarget) return;

    let cancelled = false;
    setLoading(true);
    setExpandedIds(new Set());

    async function fetchTimeline() {
      let result;

      if (isCanonical) {
        // Primary: query by canonical_project_id. Only accepted events —
        // rejected rows are noise (crawler auto_classify) and pending rows
        // are unreviewed, so neither belongs on a project timeline.
        result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .eq("canonical_project_id", queryTarget)
          .eq("review_status", "accepted")
          .order("publication_date", { ascending: true });

        // Fallback: if no canonical match, query by project name against
        // the full alias registry (display name + core name + aliases).
        if ((!result.data || result.data.length === 0) && selectedId) {
          const displayName = getDisplayName(selectedId);
          const coreName = displayName.split("(")[0].trim().replace(/\)$/, "");
          const candidates = [coreName, displayName, ...getAliases(selectedId)].filter(
            (n, i, arr) => n.length >= 4 && arr.indexOf(n) === i,
          );
          for (const name of candidates) {
            const fb = await supabase
              .from("candidate_events")
              .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
              .ilike("project_name_raw", `%${name}%`)
              .eq("review_status", "accepted")
              .order("publication_date", { ascending: true });
            if (!fb.error && fb.data && fb.data.length > 0) {
              result = fb;
              break;
            }
            result = fb; // keep last (empty) result if nothing matched
          }
        }
      } else {
        // Non-canonical project: query by raw project name
        result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .ilike("project_name_raw", `%${queryTarget.slice(0, 60)}%`)
          .eq("review_status", "accepted")
          .order("publication_date", { ascending: true });
      }

      if (cancelled) return;

      if (result.error) {
        console.error("[TimelinePage] Fetch failed:", result.error.message);
        setEvents([]);
      } else {
        const evts: TimelineEventFull[] = (result.data ?? []).map((row: Record<string, unknown>) => ({
          id: Number(row.id),
          eventType: String(row.event_type ?? ""),
          publicationDate: String(row.publication_date ?? ""),
          sourceName: String(row.source_name ?? ""),
          sourceUrl: String(row.source_url ?? ""),
          evidenceQuote: String(row.evidence_quote ?? ""),
          summary: String(row.summary ?? ""),
        }));
        setEvents(evts);
      }
      setLoading(false);
    }

    fetchTimeline();

    return () => { cancelled = true; };
  }, [queryTarget, isCanonical]);

  // Fetch project info from projects table
  useEffect(() => {
    if (!queryTarget) return;

    let cancelled = false;

    async function fetchProjectInfo() {
      const searchName = isCanonical ? getDisplayName(queryTarget) : queryTarget;
      const { data, error } = await supabase
        .from("projects")
        .select("*")
        .ilike("name", `%${searchName.slice(0, 30)}%`)
        .limit(1);

      if (cancelled || error || !data || data.length === 0) {
        if (!cancelled) setProjectInfo(null);
        return;
      }

      // Take first match
      const row = data[0] as Record<string, unknown>;
      const rawCountry = String(row.country ?? "").trim();
      const country = normalizeCountry(rawCountry);
      const confidence = String(row.confidence ?? "medium") as "high" | "medium" | "low";

      const info: Project = {
        name: String(row.name ?? ""),
        country,
        flag: String(row.flag ?? ""),
        phase: phaseFromRow(row),
        summary: String(row.summary ?? ""),
        source: {
          name: String(row.source_name ?? ""),
          url: String(row.source_url ?? ""),
          date: String(row.source_date ?? ""),
        },
        stainlessSteel: String(row.stainless_steel ?? ""),
        application: String(row.application ?? ""),
        industry: normalizeIndustry(toStr(row.industry)),
        confidence,
        procurementChain: String(row.procurement_chain ?? ""),
        waterDepthM: toNum(row.water_depth_m),
        oilCapacityBpd: toNum(row.oil_capacity_bpd),
        gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
        hullType: String(row.hull_type ?? "") || null,
        fieldName: String(row.field_name ?? "") || null,
        operatorName: String(row.operator_name ?? "") || null,
        basin: String(row.basin ?? "") || null,
        recommendationJson: null,
        createdAt: String(row.created_at ?? "") || null,
      };
      if (!cancelled) setProjectInfo(info);
    }

    fetchProjectInfo();

    return () => { cancelled = true; };
  }, [queryTarget, isCanonical]);

  // 显示全部事件类型，按日期升序，DELIVERED 恒排最后。
  // Category chips 在此之上继续收窄。
  const filteredEvents = useMemo(() => {
    let list = events;
    if (activeCategories.size !== CATEGORY_OPTIONS.length) {
      list = list.filter((e) => activeCategories.has(categorizeEvent(e.eventType)));
    }
    return sortTimelineEvents(list);
  }, [events, activeCategories]);

  // Split project options by accepted-event coverage: projects with at least
  // one accepted event stay in the main list; zero-event projects collapse
  // into the "待挖掘项目" group so they don't clutter the selector. Both
  // lists keep the alphabetical order of the registry, except pinned
  // projects: inside the "有事件" group they lead in PRIORITY_PROJECT_NAMES
  // order regardless of event count or alphabet.
  const projectGroups = useMemo(() => {
    const withEvents: ProjectOption[] = [];
    const withoutEvents: ProjectOption[] = [];
    for (const p of projects) {
      if ((eventCounts.get(p.canonicalId) ?? 0) > 0) withEvents.push(p);
      else withoutEvents.push(p);
    }
    return {
      withEvents: sortPriorityFirst(withEvents, (p) => priorityProjectRank(p.canonicalId)),
      withoutEvents,
    };
  }, [projects, eventCounts]);

  // While counts are loading, treat every project as event-having so the
  // selector doesn't flash the whole registry into the collapsed group.
  const withEventsList = countsLoading ? projects : projectGroups.withEvents;
  const withoutEventsList = countsLoading ? [] : projectGroups.withoutEvents;

  // Filtered lists for the dropdown. Search only matches zero-event projects
  // once the "待挖掘项目" group has been expanded.
  const filteredWithEvents = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return withEventsList;
    return withEventsList.filter((p) => matchesProjectQuery(p, q));
  }, [withEventsList, searchText]);

  const filteredWithoutEvents = useMemo(() => {
    if (!minedOpen) return [];
    const q = searchText.trim().toLowerCase();
    if (!q) return withoutEventsList;
    return withoutEventsList.filter((p) => matchesProjectQuery(p, q));
  }, [withoutEventsList, minedOpen, searchText]);

  // Collapsed group header is visible when not searching, or once expanded.
  const showMinedGroup = (!searchText.trim() || minedOpen) && withoutEventsList.length > 0;
  const showNoMatch = filteredWithEvents.length === 0 && !showMinedGroup;

  const toggleExpand = useCallback((id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleCategory = useCallback((cat: EventCategory) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) {
        if (next.size > 1) next.delete(cat); // keep at least one
      } else {
        next.add(cat);
      }
      return next;
    });
  }, []);

  const handleSelectProject = (id: string) => {
    setSelectedId(id);
    setSearchParams({ project: id }, { replace: true });
    setSearchText("");
    setDropdownOpen(false);
    setMinedOpen(false);
    setProjectInfo(null);
  };

  // 顶部全局搜索选中项目 — 与侧栏选择器同一套选中逻辑
  const handleHeaderProjectSelect = (p: Project) => {
    const match = projects.find((o) => o.canonicalId.toLowerCase() === p.name.toLowerCase());
    if (match) {
      handleSelectProject(match.canonicalId);
    } else {
      // 非规范名 — 走 raw-name 兜底查询，与深链行为一致
      setSelectedId("");
      setRawProjectName(p.name);
      setSearchParams({ project: p.name }, { replace: true });
      setProjectInfo(null);
    }
  };

  const selectedDisplayName = selectedId
    ? getDisplayName(selectedId)
    : rawProjectName || "";
  const selectedCountry = selectedId ? getProjectCountry(selectedId) : "";

  return (
    <>
      <PageMeta title="项目时间线" description="全球工业项目里程碑时间线" />

      <Header onProjectSelect={handleHeaderProjectSelect} />

      <div className="max-w-7xl mx-auto">
        {/* 左侧栏 — 项目选择，外壳与商机看板一致 */}
        <SidebarShell
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          collapsedLabel="Projects"
        >
          {/* Project Selector */}
          <div className="px-4 pt-4 pb-6">
            <section>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
                Project
              </label>
          <div className="relative">
            <div className="flex items-center rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md hover:border-fpso-blue/30 transition-colors">
              <Search className="ml-3 h-4 w-4 text-fpso-dim flex-shrink-0" />
              <input
                type="text"
                value={searchText || (dropdownOpen ? "" : selectedDisplayName)}
                placeholder="Search project by name or country..."
                onChange={(e) => {
                  setSearchText(e.target.value);
                  if (!dropdownOpen) setDropdownOpen(true);
                }}
                onFocus={() => {
                  setSearchText("");
                  setDropdownOpen(true);
                }}
                onBlur={() =>
                  setTimeout(() => {
                    setDropdownOpen(false);
                    setMinedOpen(false);
                  }, 200)
                }
                className="flex-1 bg-transparent px-3 py-2.5 text-sm text-fpso-fg outline-none placeholder:text-fpso-dim/50"
              />
              <ChevronDown
                className={`mr-3 h-4 w-4 text-fpso-dim transition-transform flex-shrink-0 ${
                  dropdownOpen ? "rotate-180" : ""
                }`}
              />
            </div>

            {dropdownOpen && (
              <div className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-fpso-border bg-fpso-card/95 backdrop-blur-md shadow-card">
                {showNoMatch ? (
                  <div className="px-4 py-6 text-center text-xs text-fpso-muted">No projects match.</div>
                ) : (
                  <>
                    {/* Main list: projects with accepted events, current style */}
                    {filteredWithEvents.map((p) => {
                      const hasEvents = (eventCounts.get(p.canonicalId) ?? 0) > 0;
                      return (
                        <button
                          key={p.canonicalId}
                          type="button"
                          onClick={() => handleSelectProject(p.canonicalId)}
                          className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-fpso-blue/10 ${
                            p.canonicalId === selectedId
                              ? "text-fpso-blue bg-fpso-blue/5"
                              : hasEvents
                                ? "text-fpso-fg"
                                : "text-fpso-dim/70"
                          }`}
                        >
                          <span className="truncate flex-1">{p.displayName}</span>
                          <span className="text-[11px] text-fpso-dim flex-shrink-0">{p.country}</span>
                          {!hasEvents && p.canonicalId !== selectedId && (
                            <span className="rounded bg-fpso-card px-1.5 py-0.5 text-[10px] text-fpso-dim flex-shrink-0">
                              暂无时间线
                            </span>
                          )}
                        </button>
                      );
                    })}

                    {/* Collapsed group: zero-event projects, expanded on click */}
                    {showMinedGroup && (
                      <>
                        {filteredWithEvents.length > 0 && (
                          <div className="my-1 border-t border-fpso-border" />
                        )}
                        <button
                          type="button"
                          // Keep focus on the input so the dropdown stays open
                          // while toggling the group.
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => setMinedOpen((o) => !o)}
                          className="flex w-full items-center gap-1.5 px-4 py-2 text-[11px] font-medium text-fpso-dim hover:bg-fpso-bg hover:text-fpso-muted transition-colors"
                        >
                          {minedOpen ? (
                            <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5 flex-shrink-0" />
                          )}
                          <span className="flex-1 text-left">待挖掘项目 ({withoutEventsList.length})</span>
                          <span className="text-[10px] text-fpso-dim/50 flex-shrink-0">暂无已审核事件</span>
                        </button>

                        {minedOpen &&
                          (filteredWithoutEvents.length === 0 ? (
                            <div className="px-4 py-3 text-center text-xs text-fpso-dim/60">
                              无匹配项目
                            </div>
                          ) : (
                            filteredWithoutEvents.map((p) => (
                              <button
                                key={p.canonicalId}
                                type="button"
                                onClick={() => handleSelectProject(p.canonicalId)}
                                className={`flex w-full items-center gap-3 py-2.5 pl-8 pr-4 text-left text-sm transition-colors hover:bg-fpso-bg ${
                                  p.canonicalId === selectedId
                                    ? "text-fpso-blue bg-fpso-blue/5"
                                    : "text-fpso-dim/70 hover:text-fpso-muted"
                                }`}
                              >
                                <span className="truncate flex-1">{p.displayName}</span>
                                <span className="text-[11px] text-fpso-dim flex-shrink-0">{p.country}</span>
                              </button>
                            ))
                          ))}
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
            </section>
          </div>
        </SidebarShell>

      <main
        className="flex-1 min-w-0 px-4 py-8 md:px-6 transition-all duration-300 ease-in-out max-md:!ml-0"
        style={{ marginLeft: sidebarCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED }}
      >
        {/* page header — 统一 PageHeader */}
        <PageHeader
          title={<span className="neon-glow">项目时间线</span>}
          subtitle="查看项目里程碑和关键事件"
          actions={
            <button
              onClick={() => navigate(-1)}
              className="text-xs text-fpso-muted hover:text-fpso-fg transition-colors"
            >
              ← Back
            </button>
          }
        />

        {/* Event Type Filters */}
        <section className="mb-8">
          <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
            Event Type
          </label>
          <div className="flex flex-wrap gap-2">
            {CATEGORY_OPTIONS.map((cat) => {
              const active = activeCategories.has(cat.key);
              return (
                <button
                  key={cat.key}
                  type="button"
                  onClick={() => toggleCategory(cat.key)}
                  className="inline-flex items-center rounded-md px-3 py-1.5 text-xs font-medium transition-all border"
                  style={{
                    borderColor: active ? cat.color : "rgb(30 40 68 / 0.6)",
                    backgroundColor: active ? `${cat.color}18` : "transparent",
                    color: active ? cat.color : "#64748b",
                  }}
                >
                  {cat.label}
                </button>
              );
            })}
          </div>
        </section>

        {/* Timeline */}
        <section className="mb-10">
          <h2 className="mb-6 text-sm font-semibold text-fpso-fg">
            Timeline
            {selectedDisplayName && (
              <span className="ml-2 text-xs font-normal text-fpso-dim">
                — {selectedDisplayName}
              </span>
            )}
          </h2>

          {loading || countsLoading ? (
            <div className="flex items-center justify-center py-16">
              <span className="text-sm text-fpso-muted">Loading timeline…</span>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center rounded-lg border border-fpso-border bg-fpso-card/70">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-12 w-12 text-fpso-dim mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <p className="text-sm text-fpso-muted">
                {events.length === 0
                  ? "该项目暂无时间线事件。"
                  : "没有符合当前筛选条件的事件。"}
              </p>
              <p className="text-xs text-fpso-dim mt-1 max-w-md leading-relaxed">
                {events.length === 0
                  ? "可能是早期阶段项目尚无公开里程碑，或历史已交付/噪音项目未收录事件。时间线仅显示已审核通过（accepted）的事件，未审核或已拒绝的事件不会展示。"
                  : "数据来自 candidate_events，仅显示已审核通过（accepted）的事件。"}
              </p>
            </div>
          ) : (
            <div key={selectedId} className="animate-fade-in relative">
              {/* Vertical line */}
              <div className="absolute left-[5px] top-2 bottom-2 w-0.5 bg-fpso-border" />

              <div className="space-y-5">
                {filteredEvents.map((evt) => {
                  const expanded = expandedIds.has(evt.id);
                  const dotColor = timelineDotStyle(evt.eventType);
                  const hasEvidence = Boolean(evt.evidenceQuote);
                  const hasExtra = hasEvidence;

                  return (
                    <div key={evt.id} className="relative flex gap-5">
                      {/* Dot — 事件圆点 + 光晕 */}
                      <div
                        className="relative z-10 mt-1 h-3.5 w-3.5 flex-shrink-0 rounded-full border-2 border-fpso-card"
                        style={{
                          backgroundColor: dotColor,
                          boxShadow: `0 0 12px ${dotColor}, 0 0 4px ${dotColor}`,
                        }}
                      />

                      {/* Event card */}
                      <div
                        className={`flex-1 min-w-0 rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md transition-all hover:shadow-hover hover:border-fpso-blue/30 cursor-default ${
                          hasExtra ? "cursor-pointer" : ""
                        }`}
                        onClick={() => hasExtra && toggleExpand(evt.id)}
                      >
                        {/* Header row */}
                        <div className="flex items-center justify-between gap-3 px-4 py-3">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <span
                              className="inline-flex items-center rounded px-2 py-0.5 text-[11px] font-semibold"
                              style={{
                                backgroundColor: `${dotColor}18`,
                                color: dotColor,
                              }}
                            >
                              {formatEventType(evt.eventType)}
                            </span>
                            {hasExtra && (
                              <span className="text-fpso-dim/60">
                                {expanded ? (
                                  <ChevronDown className="h-3.5 w-3.5" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5" />
                                )}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-fpso-dim font-mono flex-shrink-0 tabular-nums">
                            {evt.publicationDate || "—"}
                          </span>
                        </div>

                        {/* Summary */}
                        {evt.summary && (
                          <p className="px-4 pb-1 text-xs text-fpso-fg/80 leading-relaxed">
                            {evt.summary}
                          </p>
                        )}

                        {/* Expandable evidence */}
                        {expanded && evt.evidenceQuote && (
                          <blockquote className="mx-4 mb-3 border-l-2 border-fpso-blue/30 pl-3 text-[11px] text-fpso-muted italic leading-relaxed">
                            &ldquo;{evt.evidenceQuote}&rdquo;
                          </blockquote>
                        )}

                        {/* Source link */}
                        <div className="px-4 pb-3 flex items-center gap-1.5">
                          {evt.sourceUrl ? (
                            <a
                              href={evt.sourceUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-[10px] text-fpso-blue/70 hover:text-fpso-blue hover:underline inline-flex items-center gap-1 transition-colors"
                            >
                              {evt.sourceName || evt.sourceUrl}
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : (
                            <span className="text-[10px] text-fpso-dim">
                              {evt.sourceName || "—"}
                            </span>
                          )}
                          <SourceLinkBadge url={evt.sourceUrl} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* Project Info Card */}
        {projectInfo && (
          <section className="rounded-lg border border-fpso-border bg-fpso-card/70 backdrop-blur-md p-5">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
              Project Info
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <InfoItem label="Name" value={projectInfo.name} />
              <InfoItem
                label="Country"
                value={`${projectInfo.flag ? projectInfo.flag + " " : ""}${projectInfo.country}`}
              />
              <InfoItem label="Phase" value={projectInfo.phase ?? "Unknown"} />
              <InfoItem label="Industry" value={projectInfo.industry ?? "FPSO"} />
              {projectInfo.waterDepthM != null && (
                <InfoItem
                  label="Water Depth"
                  value={`${projectInfo.waterDepthM.toLocaleString()} m`}
                  icon={<Anchor className="h-3 w-3" />}
                />
              )}
              {projectInfo.oilCapacityBpd != null && (
                <InfoItem
                  label="Oil Capacity"
                  value={`${projectInfo.oilCapacityBpd.toLocaleString()} bpd`}
                  icon={<Gauge className="h-3 w-3" />}
                />
              )}
              {projectInfo.gasCapacityMmcmd != null && (
                <InfoItem
                  label="Gas Capacity"
                  value={`${projectInfo.gasCapacityMmcmd.toLocaleString()} MMcmd`}
                  icon={<Waves className="h-3 w-3" />}
                />
              )}
              {projectInfo.hullType && <InfoItem label="Hull Type" value={projectInfo.hullType} />}
              {projectInfo.fieldName && <InfoItem label="Field" value={projectInfo.fieldName} />}
              {projectInfo.operatorName && (
                <InfoItem label="Operator" value={projectInfo.operatorName} />
              )}
              {projectInfo.basin && <InfoItem label="Basin" value={projectInfo.basin} />}
              {projectInfo.confidence && (
                <InfoItem label="Confidence" value={projectInfo.confidence} />
              )}
            </div>
          </section>
        )}
      </main>
      </div>

      {/* Footer */}
      <footer className="mt-auto border-t border-fpso-border bg-fpso-bg">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 py-5 md:flex-row md:px-6">
          <span className="text-xs text-fpso-dim">
            Timeline data from candidate_events. For internal analysis only.
          </span>
          <span className="text-xs text-fpso-dim">
            {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}
          </span>
        </div>
      </footer>
    </>
  );
}

/** Simple labeled info item for the project info card. */
function InfoItem({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <span className="block text-[10px] font-semibold uppercase tracking-wider text-fpso-dim mb-0.5">
        {label}
      </span>
      <span className="inline-flex items-center gap-1.5 text-xs text-fpso-fg">
        {icon}
        {value}
      </span>
    </div>
  );
}
