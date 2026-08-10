/**
 * ProjectTimelinePage — 全屏项目时间线视图
 * 路由: /project-timeline?project={canonicalId}
 * 从 Dashboard 详情弹窗的 Timeline 标签跳转访问。
 */

import { useEffect, useMemo, useState, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import { supabase } from "@/db/supabase";
import {
  getAllCanonicalIds,
  getDisplayName,
  getProjectCountry,
} from "@/data/project_aliases";
import type { Project } from "@/data/projects";
import { countryToFlagEmoji, COUNTRY_ALIASES } from "@/data/projects";
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

const CATEGORY_OPTIONS: { key: EventCategory; label: string; color: string }[] = [
  { key: "PRODUCTION", label: "投产", color: "#10b981" },
  { key: "CONTRACT", label: "合同", color: "#00d4ff" },
  { key: "EIA", label: "EIA/计划", color: "#ff9f43" },
  { key: "REGULATORY", label: "监管/许可", color: "#f472b6" },
  { key: "OTHER", label: "其他", color: "#94a3b8" },
];

function categorizeEvent(eventType: string): EventCategory {
  const et = eventType.toUpperCase();
  if (/PRODUCTION_START|FIRST_OIL/.test(et)) return "PRODUCTION";
  if (/CONTRACT|AWARDED/.test(et)) return "CONTRACT";
  if (/EIA|DEVELOPMENT_PLAN/.test(et)) return "EIA";
  if (/REGULATORY|PERMIT|LICENSE|GRANTED|CONSENT|PUBLIC_NOTICE/.test(et)) return "REGULATORY";
  return "OTHER";
}

function timelineDotColor(eventType: string): string {
  const cat = categorizeEvent(eventType);
  switch (cat) {
    case "PRODUCTION": return "bg-fpso-green";
    case "CONTRACT": return "bg-fpso-blue";
    case "EIA": return "bg-fpso-orange";
    case "REGULATORY": return "bg-pink-400"; // tailwind pink
    default: return "bg-fpso-muted";
  }
}

function timelineDotStyle(eventType: string): string {
  const cat = categorizeEvent(eventType);
  switch (cat) {
    case "PRODUCTION": return "#10b981";
    case "CONTRACT": return "#00d4ff";
    case "EIA": return "#ff9f43";
    case "REGULATORY": return "#f472b6";
    default: return "#94a3b8";
  }
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

// ---- Component ----

export default function ProjectTimelinePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Project selection
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

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

    // Determine initial selection
    const urlProject = searchParams.get("project");
    const urlProjectName = searchParams.get("projectName");

    if (urlProject && ids.includes(urlProject)) {
      setSelectedId(urlProject);
    } else if (urlProjectName) {
      // Fallback: project not in alias registry — use raw name
      setRawProjectName(urlProjectName);
      setSelectedId(""); // will trigger fallback query
    } else if (list.length > 0) {
      setSelectedId(list[0].canonicalId);
      setSearchParams({ project: list[0].canonicalId }, { replace: true });
    }
  }, []);

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
        // Primary: query by canonical_project_id
        result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .eq("canonical_project_id", queryTarget)
          .order("publication_date", { ascending: true });

        // Fallback: if no canonical match, query by display name
        if ((!result.data || result.data.length === 0) && selectedId) {
          const displayName = getDisplayName(selectedId);
          result = await supabase
            .from("candidate_events")
            .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
            .ilike("project_name_raw", `%${displayName.slice(0, 40)}%`)
            .order("publication_date", { ascending: true });
        }
      } else {
        // Non-canonical project: query by raw project name
        result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .ilike("project_name_raw", `%${queryTarget.slice(0, 60)}%`)
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

  // Filter events by active categories
  const filteredEvents = useMemo(() => {
    if (activeCategories.size === CATEGORY_OPTIONS.length) return events;
    return events.filter((e) => activeCategories.has(categorizeEvent(e.eventType)));
  }, [events, activeCategories]);

  // Filtered project list for dropdown
  const filteredProjects = useMemo(() => {
    if (!searchText.trim()) return projects;
    const q = searchText.toLowerCase();
    return projects.filter(
      (p) =>
        p.displayName.toLowerCase().includes(q) ||
        p.country.toLowerCase().includes(q) ||
        p.canonicalId.toLowerCase().includes(q),
    );
  }, [projects, searchText]);

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
    setProjectInfo(null);
  };

  const selectedDisplayName = selectedId
    ? getDisplayName(selectedId)
    : rawProjectName || "";
  const selectedCountry = selectedId ? getProjectCountry(selectedId) : "";

  return (
    <>
      <PageMeta title="Project Timeline" description="FPSO project milestone timeline" />

      <Header
        rightContent={
          <button
            onClick={() => navigate(-1)}
            className="text-xs text-fpso-muted hover:text-fpso-fg transition-colors"
          >
            ← Back
          </button>
        }
      />

      <div className="mx-auto max-w-4xl px-6 py-8">
        {/* Project Selector */}
        <section className="mb-6">
          <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
            Project
          </label>
          <div className="relative">
            <div className="flex items-center rounded-lg border border-white/5 bg-fpso-card/60 backdrop-blur-md hover:border-white/10 transition-colors">
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
                onBlur={() => setTimeout(() => setDropdownOpen(false), 200)}
                className="flex-1 bg-transparent px-3 py-2.5 text-sm text-fpso-fg outline-none placeholder:text-fpso-dim/50"
              />
              <ChevronDown
                className={`mr-3 h-4 w-4 text-fpso-dim transition-transform flex-shrink-0 ${
                  dropdownOpen ? "rotate-180" : ""
                }`}
              />
            </div>

            {dropdownOpen && (
              <div className="absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-white/5 bg-fpso-card/90 backdrop-blur-md shadow-xl">
                {filteredProjects.length === 0 ? (
                  <div className="px-4 py-6 text-center text-xs text-fpso-muted">No projects match.</div>
                ) : (
                  filteredProjects.map((p) => (
                    <button
                      key={p.canonicalId}
                      type="button"
                      onClick={() => handleSelectProject(p.canonicalId)}
                      className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-fpso-blue/10 ${
                        p.canonicalId === selectedId
                          ? "text-fpso-blue bg-fpso-blue/5"
                          : "text-fpso-fg"
                      }`}
                    >
                      <span className="truncate flex-1">{p.displayName}</span>
                      <span className="text-[11px] text-fpso-dim flex-shrink-0">{p.country}</span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </section>

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
                    color: active ? cat.color : "#94a3b8",
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

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <span className="text-sm text-fpso-muted">Loading timeline…</span>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center rounded-lg border border-white/5 bg-fpso-card/40">
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
                  ? "No milestone events found for this project."
                  : "No events match the selected filters."}
              </p>
              <p className="text-xs text-fpso-dim mt-1">
                {events.length === 0
                  ? "No matching events found in candidate_events. Data may appear after the next crawl."
                  : "Timeline data is sourced from candidate_events."}
              </p>
            </div>
          ) : (
            <div key={selectedId} className="animate-fade-in relative">
              {/* Vertical line */}
              <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-fpso-border" />

              <div className="space-y-5">
                {filteredEvents.map((evt) => {
                  const expanded = expandedIds.has(evt.id);
                  const dotColor = timelineDotStyle(evt.eventType);
                  const hasEvidence = Boolean(evt.evidenceQuote);
                  const hasExtra = hasEvidence;

                  return (
                    <div key={evt.id} className="relative flex gap-5">
                      {/* Dot */}
                      <div
                        className="relative z-10 mt-1.5 h-3 w-3 flex-shrink-0 rounded-full border-2 border-fpso-card"
                        style={{ backgroundColor: dotColor, boxShadow: `0 0 8px ${dotColor}80` }}
                      />

                      {/* Event card */}
                      <div
                        className={`flex-1 min-w-0 rounded-lg border border-white/5 bg-fpso-card/60 backdrop-blur-md transition-shadow hover:shadow-lg cursor-default ${
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
          <section className="rounded-lg border border-white/5 bg-fpso-card/60 backdrop-blur-md p-5">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
              Project Info
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <InfoItem label="Name" value={projectInfo.name} />
              <InfoItem
                label="Country"
                value={`${projectInfo.flag ? projectInfo.flag + " " : ""}${projectInfo.country}`}
              />
              <InfoItem label="Status" value={projectInfo.status} />
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
      </div>

      {/* Footer */}
      <footer className="mt-auto border-t border-white/5 bg-fpso-bg">
        <div className="mx-auto flex max-w-4xl flex-col items-center justify-between gap-2 px-6 py-5 md:flex-row">
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
