/**
 * Business Opportunity Discovery
 * 深色数据终端风格单页面：全球 FPSO 项目不锈钢商机挖掘系统
 * 数据源：Supabase projects + candidate_events 合并显示
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from "recharts";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project, MaterialMatchResult } from "@/data/projects";
import { countryCoordinates, sampleProjects, countryToFlagEmoji, COUNTRY_ALIASES, normalizeIndustry } from "@/data/projects";
import { normalizeProjectName, getDisplayName, sortPriorityFirst, priorityProjectRankByName } from "@/data/project_aliases";
import { supabase, fetchAllRows } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { useTimelineEventCounts } from "@/hooks/useTimelineEventCounts";
import { useSubscription } from "@/hooks/useSubscription";
import { useRequireLogin } from "@/hooks/useRequireLogin";
import { matchMaterials, specsFromRow, hasAnySpecs, parseCorrosiveMedia, getCorrosiveMediaTags, getCorrosiveMediaDetails } from "@/lib/material_matcher";
import { exportOpportunityList } from "@/lib/export_opportunities";
import { filterMatureProjects, hasTimelineData } from "@/lib/project_maturity";
import { projectMatchesSearch } from "@/lib/project_search";
import { scoreOpportunity, scoreBadgeClass } from "@/lib/opportunity_scorer";
import {
  PHASES, PHASE_UNKNOWN, PHASE_HEX, PHASE_SEGMENTS, PHASE_UNLIT,
  phaseGroup, phaseColorClass, phaseDotClass, phaseBorderLClass,
  phaseProgressIndex, phaseLabel, phaseFromRow,
} from "@/lib/project_phase";
import { analyzeProjectScenario, assessOpportunity, type AIResult, type ScenarioAnalysis, type OpportunityAssessment } from "@/lib/ai_analyst";
import { usePushAnalysis, usePushAnalysisState } from "@/hooks/usePushAnalysis";
import PushAnalysisPanel, { PushSourceBadge } from "@/components/dashboard/PushAnalysisPanel";
import BattleCardWrapper from "@/components/dashboard/BattleCard";
import OutreachModal from "@/components/dashboard/OutreachModal";
import FollowUpStatus from "@/components/dashboard/FollowUpStatus";
import GlobalSearch from "@/components/dashboard/GlobalSearch";
import { Building2, Hammer, CalendarDays, PlusCircle, Anchor, Waves, Gauge, Globe, BarChart3 } from "lucide-react";
import FilterSidebar from "@/components/dashboard/FilterSidebar";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";

/** A single timeline milestone from candidate_events. */
interface TimelineEvent {
  id: number;
  eventType: string;
  publicationDate: string;
  sourceName: string;
  sourceUrl: string;
  evidenceQuote: string;
  summary: string;
}

/** Human-readable labels for known event_type values. */
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

/** Human-readable next-milestone labels for the card preview. */
const NEXT_MILESTONE_LABELS: Record<string, string> = {
  "EIA_SUBMITTED": "环评审批中",
  "FID_CONFIRMED": "FID已确认",
  "FPSO_CONTRACT_AWARDED": "合同已授予",
  "PRODUCTION_START": "已投产",
  "DEVELOPMENT_CONSENT_GRANTED": "开发许可已批准",
  "DEVELOPMENT_PLAN_SUBMITTED": "开发计划已提交",
  "DEVELOPMENT_PLAN_UPDATED": "开发计划已更新",
  "PERMIT_GRANTED": "许可已批准",
  "LICENSE_GRANTED": "许可证已授予",
  "FIELD_DEVELOPMENT_PLAN": "油田开发规划中",
  "FIRST_OIL": "首次产油",
  "CONTRACT_ANNOUNCEMENT": "合同公告",
  "VENDOR_REGISTRATION_ACTION": "供应商注册",
  "REGULATORY_DATA": "监管备案",
  "PUBLIC_NOTICE": "公示中",
  "ARTICLE_MENTION": "媒体报道",
  "BACKFILL_COUNTRY": "数据回填",
};

/** A single candidate_events row for milestone computation. */
interface MilestoneEvent {
  eventType: string;
  publicationDate: string;
}

function formatEventType(et: string): string {
  return EVENT_TYPE_LABELS[et] ?? et.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Timeline dot color by event category. */
function timelineDotColor(eventType: string): string {
  const et = eventType.toUpperCase();
  if (/PRODUCTION_START|FIRST_OIL/.test(et)) return "bg-fpso-green";
  if (/CONTRACT|AWARDED|GRANTED|LICENSE/.test(et)) return "bg-fpso-blue";
  if (/EIA|PLAN|REGULATORY|PERMIT/.test(et)) return "bg-fpso-orange";
  return "bg-fpso-muted";
}

interface Stats {
  total: number;
  early: number;
  mid: number;
  late: number;
  addedThisWeek: number;
}

function getStats(projects: Project[]): Stats {
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  return {
    total: projects.length,
    early: projects.filter((p) => phaseGroup(p.phase) === "early").length,
    mid: projects.filter((p) => phaseGroup(p.phase) === "mid").length,
    late: projects.filter((p) => phaseGroup(p.phase) === "late").length,
    addedThisWeek: projects.filter((p) => {
      if (!p.source.date) return false;
      const d = new Date(p.source.date);
      return !isNaN(d.getTime()) && d >= weekAgo;
    }).length,
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



/** 环形图顺序色 — 青→深蓝单色系渐变，最亮给最大扇区 */
const COUNTRY_CHART_COLORS = [
  "#00d4ff", "#0ea5e9", "#2563eb", "#1d4ed8",
  "#1e40af", "#1e3a8a", "#172554",
];

/** Source badge for AI vs rule-engine output. */
function SourceBadge({ source }: { source: "ai" | "rules" }) {
  return source === "ai" ? (
    <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-green/15 px-1.5 py-0.5 text-[10px] font-semibold text-fpso-green">
      AI 推断
    </span>
  ) : (
    <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-muted/15 px-1.5 py-0.5 text-[10px] font-semibold text-fpso-muted">
      规则引擎
    </span>
  );
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
    // Technical specs
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    recommendationJson: toStr(row.recommendation_json),
    createdAt: toStr(row.created_at),
    corrosiveMedia: parseCorrosiveMedia(row.corrosive_media),
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
    phase: phaseFromRow(row),
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
    // Technical specs from candidate_events
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    recommendationJson: null,
    createdAt: toStr(row.created_at),
    corrosiveMedia: parseCorrosiveMedia(row.corrosive_media),
  };
}


/** A single dashboard project row — its own component so each card can
 *  lazy-load the AI analysis only when scrolled into view (one LLM call per
 *  project, not one per rendered project at page load). */
function DashboardProjectCard({
  project,
  onOpen,
  milestoneMap,
  timelineEventCounts,
  showAllProjects,
}: {
  project: Project;
  onOpen: (p: Project) => void;
  milestoneMap: Map<string, { label: string; year: string }>;
  timelineEventCounts: Map<string, number>;
  showAllProjects: boolean;
}) {
  const rowRef = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);

  // AI 分析仅在卡片进入视口后触发 — 规则引擎结果先行显示，AI 返回后替换
  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const { analysis, loading } = usePushAnalysisState(project, inView);

  return (
    <motion.div
      ref={rowRef}
      layout
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      onClick={() => onOpen(project)}
      className={`project-row group cursor-pointer border-b border-white/5 border-l-4 px-5 py-5 last:border-b-0 transition-all hover:bg-fpso-blue/[0.04] hover:border-white/10 ${phaseBorderLClass(project.phase)}`}
    >
              {/* Row 1: status dot + name + country + source */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-center gap-2.5">
                  <span
                    className={`mt-0.5 h-2 w-2 flex-shrink-0 rounded-full ${phaseDotClass(project.phase)}`}
                    style={{ boxShadow: `0 0 6px currentColor` }}
                  />
                  <h3 className="truncate text-sm font-semibold text-fpso-fg group-hover:text-white transition-colors">
                    {project.name}
                  </h3>
                  <span className="inline-flex flex-shrink-0 items-center gap-1 rounded bg-fpso-bg/80 px-1.5 py-0.5 text-[11px] text-fpso-muted ring-1 ring-fpso-border/50">
                    {project.flag && <span className="text-xs leading-none">{project.flag}</span>}
                    <span className="max-w-[100px] truncate">{project.country}</span>
                  </span>
                </div>

                <div className="flex flex-shrink-0 items-center gap-2">
                  {project.source.url ? (
                    <a
                      href={project.source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="external-link inline-flex items-center gap-1 text-[11px] text-fpso-blue/70 hover:text-fpso-blue transition-colors"
                    >
                      <span className="max-w-[120px] truncate">{project.source.name}</span>
                      <span className="text-[0.8em] leading-none">↗</span>
                    </a>
                  ) : (
                    <span className="text-[11px] text-fpso-dim">{project.source.name || "—"}</span>
                  )}
                  <span className="text-[10px] text-fpso-dim font-mono tabular-nums">{project.source.date}</span>
                  {(() => {
                    const candidates = [project.source.date, project.createdAt].filter(Boolean) as string[];
                    const latest = candidates.sort().pop()?.slice(0, 10);
                    if (!latest || latest === project.source.date?.slice(0, 10)) return null;
                    return (
                      <span className="text-[10px] text-fpso-muted font-mono tabular-nums">
                        Updated: {latest}
                      </span>
                    );
                  })()}
                </div>
              </div>

              {/* Row 2: badges + tech specs */}
              <div className="mt-2.5 ml-4 flex flex-wrap items-center gap-1.5">
                {/* Industry badge */}
                {(project.industry ?? "FPSO") && (
                  <span className="inline-flex items-center rounded bg-fpso-blue/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fpso-blue ring-1 ring-fpso-blue/15">
                    {project.industry}
                  </span>
                )}
                {/* Confidence badge */}
                {project.confidence && (
                  <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${confidenceBadgeClass(project.confidence)}`}>
                    {project.confidence}
                  </span>
                )}
                {/* Opportunity Score badge */}
                {(() => {
                  const scoreResult = scoreOpportunity(project);
                  return (
                    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${scoreBadgeClass(scoreResult.grade)}`}>
                      {scoreResult.grade}{scoreResult.totalScore}
                    </span>
                  );
                })()}
                {/* Phase text */}
                <span className={`text-[11px] font-medium ${phaseColorClass(project.phase)}`}>
                  {phaseLabel(project.phase)}
                </span>
                {/* 待挖掘 badge: timeline has no linked events */}
                {showAllProjects && !hasTimelineData(project, timelineEventCounts) && (
                  <span
                    className="inline-flex items-center rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-400 ring-1 ring-amber-400/20"
                    title="暂无足够商机数据，已加入待挖掘池"
                  >
                    待挖掘
                  </span>
                )}
                {/* Separator */}
                {(project.waterDepthM != null || project.oilCapacityBpd != null || project.gasCapacityMmcmd != null) && (
                  <span className="mx-0.5 h-3 w-px bg-fpso-border/50 flex-shrink-0" />
                )}
                {/* Tech specs */}
                {project.waterDepthM != null && (
                  <span className="inline-flex items-center gap-1 text-[10px] text-fpso-dim font-mono" title="Water Depth">
                    <Anchor className="h-3 w-3 text-fpso-dim/60 flex-shrink-0" />
                    {project.waterDepthM.toLocaleString()}m
                  </span>
                )}
                {project.oilCapacityBpd != null && (
                  <span className="inline-flex items-center gap-1 text-[10px] text-fpso-dim font-mono" title="Oil Capacity">
                    <Gauge className="h-3 w-3 text-fpso-dim/60 flex-shrink-0" />
                    {project.oilCapacityBpd.toLocaleString()} bpd
                  </span>
                )}
                {project.gasCapacityMmcmd != null && (
                  <span className="inline-flex items-center gap-1 text-[10px] text-fpso-dim font-mono" title="Gas Capacity">
                    <Waves className="h-3 w-3 text-fpso-dim/60 flex-shrink-0" />
                    {project.gasCapacityMmcmd.toLocaleString()} MMcmd
                  </span>
                )}
                {/* Hull type */}
                {project.hullType && (
                  <span className="inline-flex items-center gap-1 text-[10px] text-fpso-dim font-mono">
                    <span className="text-fpso-dim/60">{project.hullType}</span>
                  </span>
                )}
              </div>

              {/* Row 3: summary */}
              {project.summary && (
                <p className="mt-2 ml-4 line-clamp-1 text-[11px] leading-relaxed text-fpso-muted/80">
                  {project.summary}
                </p>
              )}

              {/* Row 4: procurement chain tags */}
              {project.procurementChain && (
                <div className="mt-2 ml-4 flex flex-wrap items-center gap-1">
                  <span className="text-[9px] font-semibold uppercase tracking-wider text-fpso-dim/60 mr-0.5">Procurement</span>
                  {project.procurementChain.split(/,\s*/).filter(Boolean).map((entity) => (
                    <span
                      key={entity}
                      className="inline-flex items-center rounded bg-fpso-green/[0.07] px-1.5 py-0.5 text-[10px] font-medium text-fpso-green/80 ring-1 ring-fpso-green/10 procurement-tag"
                    >
                      {entity}
                    </span>
                  ))}
                </div>
              )}

                  {/* Row 5: AI 个性化商机分析 — LLM 请求中显示加载态，AI 返回后替换 */}
                  {loading ? (
                    <div className="mt-2 ml-4 flex flex-wrap items-center gap-1.5">
                      <span className="text-[9px] font-semibold uppercase tracking-wider text-fpso-dim/60 mr-0.5">商机分析</span>
                      <span className="inline-flex items-center rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400 animate-pulse">
                        AI 分析中…
                      </span>
                    </div>
                  ) : analysis && (analysis.procurement_window.range !== "待补充" || analysis.recommended_materials.length > 0 || analysis.recommended_products.length > 0) && (
                    <div className="mt-2 ml-4 flex flex-wrap items-center gap-1.5">
                      <span className="text-[9px] font-semibold uppercase tracking-wider text-fpso-dim/60 mr-0.5">商机分析</span>
                      {analysis.procurement_window.range !== "待补充" && (
                        <span
                          title={analysis.procurement_window.reasoning}
                          className="inline-flex items-center rounded bg-fpso-blue/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-blue ring-1 ring-fpso-blue/10"
                        >
                          采购时间窗 {analysis.procurement_window.range}
                        </span>
                      )}
                      {analysis.recommended_materials.slice(0, 3).map((m) => (
                        <span
                          key={m.grade}
                          title={m.reason}
                          className="inline-flex items-center rounded bg-fpso-green/[0.07] px-1.5 py-0.5 text-[10px] font-mono font-medium text-fpso-green/80 ring-1 ring-fpso-green/10"
                        >
                          {m.grade}
                        </span>
                      ))}
                      {analysis.recommended_products.slice(0, 3).map((p) => (
                        <span
                          key={p.product}
                          title={p.reason}
                          className="inline-flex items-center rounded bg-fpso-orange/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-orange/80 ring-1 ring-fpso-orange/10"
                        >
                          {p.product}
                        </span>
                      ))}
                      <PushSourceBadge source={analysis.source} />
                    </div>
                  )}
              {/* Phase progress bar — 9 lifecycle segments */}
              {(() => {
                const progress = phaseProgressIndex(project.phase);
                return (
                  <div className="mt-2.5 ml-4 flex gap-1" style={{ height: 4 }}>
                    {PHASE_SEGMENTS.map((seg, i) => (
                      <div
                        key={seg.label}
                        title={`${seg.label}${i < progress ? " ✓" : ""}`}
                        className="rounded-full transition-colors duration-500"
                        style={{
                          flex: 1,
                          backgroundColor: i < progress ? seg.color : PHASE_UNLIT,
                        }}
                      />
                    ))}
                  </div>
                );
              })()}

              {/* Next milestone + corrosive media tags */}
              {(() => {
                const canonicalId = normalizeProjectName(project.name);
                const ms = canonicalId ? milestoneMap.get(canonicalId) : undefined;
                const cmTags = getCorrosiveMediaTags(project.corrosiveMedia);
                if (!ms && cmTags.length === 0) {
                  return (
                    <p className="mt-1 ml-4 text-[10px] text-fpso-muted/50">暂无里程碑</p>
                  );
                }
                return (
                  <div className="mt-1 ml-4 flex items-center gap-2 flex-wrap">
                    {ms ? (
                      <p className="text-[10px] text-fpso-blue/70">
                        Next: {ms.label}{ms.year ? ` ${ms.year}` : ""}
                      </p>
                    ) : (
                      <p className="text-[10px] text-fpso-muted/50">暂无里程碑</p>
                    )}
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
    </motion.div>
  );
}
export default function DashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCountry, setSelectedCountry] = useState("All Countries");
  const [selectedIndustry, setSelectedIndustry] = useState("All Industries");
  const [selectedConfidence, setSelectedConfidence] = useState("High & Medium");
  const [selectedPhases, setSelectedPhases] = useState<Set<string>>(
    // Default: all 10 phase chips selected (9 lifecycle phases + Unknown) — no phase hidden by default.
    () => new Set([...PHASES, PHASE_UNKNOWN]),
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  // Default: show all projects (mature filter off until user opts in via sidebar).
  const [showAllProjects, setShowAllProjects] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [milestoneMap, setMilestoneMap] = useState<Map<string, { label: string; year: string }>>(new Map());
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [modalTab, setModalTab] = useState<"overview" | "timeline">("overview");
  const [battleCardProject, setBattleCardProject] = useState<Project | null>(null);
  const [outreachProject, setOutreachProject] = useState<Project | null>(null);
  const [aiScenario, setAiScenario] = useState<AIResult<ScenarioAnalysis> | null>(null);
  const [aiAssessment, setAiAssessment] = useState<AIResult<OpportunityAssessment> | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  // AI 个性化分析（同飞书推送）— 规则引擎结果立即显示，AI 返回后更新
  const pushAnalysis = usePushAnalysis(selectedProject);
  const { version, status: connectionStatus } = useProjectRealtime();
  const timelineEventCounts = useTimelineEventCounts(version);
  const { isFollowing, toggleFollowProject } = useSubscription();
  const requireLogin = useRequireLogin();

  // ---- 从 Supabase 获取项目数据 ----
  useEffect(() => {
    console.log("[Dashboard] === Starting data fetch ===");
    console.log("[Dashboard] supabase client: initialized");

    console.log(
      "地图已更换，若光点位置偏移，请调整 src/data/projects.ts 中的 countryCoordinates 百分比。"
    );

    let cancelled = false;

    async function fetchTable(tableName: "projects" | "candidate_events"): Promise<Project[]> {
      const start = performance.now();
      // Paginated loop fetch — plain select("*") caps at 1000 rows.
      const { data, error } = await fetchAllRows(
        tableName,
        "*",
        tableName === "projects" ? { orderBy: "name" } : { orderBy: "id" },
      );
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
        console.table(merged.map((p) => ({ name: p.name, country: p.country, phase: p.phase })));
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

  // ---- Fetch milestone data for next-milestone preview ----
  useEffect(() => {
    let cancelled = false;

    async function fetchMilestones() {
      const { data, error } = await fetchAllRows(
        "candidate_events",
        "canonical_project_id, event_type, publication_date",
        { orderBy: "id", notNullColumn: "canonical_project_id" },
      );

      if (cancelled || error || !data) return;

      // Group by canonical_project_id, keep latest event per project
      const latest = new Map<string, MilestoneEvent>();
      for (const row of data) {
        const pid = String(row.canonical_project_id ?? "").trim();
        if (!pid) continue;
        const date = String(row.publication_date ?? "").trim();
        const cur = latest.get(pid);
        if (!cur || date > cur.publicationDate) {
          latest.set(pid, { eventType: String(row.event_type ?? ""), publicationDate: date });
        }
      }

      const map = new Map<string, { label: string; year: string }>();
      for (const [pid, evt] of latest) {
        const label = NEXT_MILESTONE_LABELS[evt.eventType]
          ?? evt.eventType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        const year = evt.publicationDate ? evt.publicationDate.slice(0, 4) : "";
        map.set(pid, { label, year });
      }

      if (!cancelled) setMilestoneMap(map);
    }

    fetchMilestones();

    return () => { cancelled = true; };
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
    // 置信度筛选前先存快照：置顶项目豁免置信度筛选（三个置顶被强制
    // low 置信度，默认 High & Medium 会把它们全部排除），筛选后加回。
    // 只豁免置信度，国家/行业/搜索/成熟度筛选仍然生效。
    const beforeConfidenceFilter = result;
    if (selectedConfidence === "High & Medium") {
      result = result.filter(
        (p) => (p.confidence ?? "medium") !== "low",
      );
    } else if (selectedConfidence !== "All") {
      result = result.filter(
        (p) => (p.confidence ?? "medium") === selectedConfidence.toLowerCase(),
      );
    }
    if (selectedConfidence !== "All") {
      const pinnedExcluded = beforeConfidenceFilter.filter(
        (p) => !result.includes(p) && priorityProjectRankByName(p.name) >= 0,
      );
      result = [...result, ...pinnedExcluded];
    }
    if (selectedPhases.size > 0) {
      const beforePhaseFilter = result;
      result = result.filter((p) => selectedPhases.has(phaseLabel(p.phase)));
      // 置顶项目豁免阶段筛选：即使其阶段未勾选也强制保留，
      // 其余项目照常遵守阶段筛选。
      const pinnedExcluded = beforePhaseFilter.filter(
        (p) => !result.includes(p) && priorityProjectRankByName(p.name) >= 0,
      );
      result = [...result, ...pinnedExcluded];
    }
    const searchActive = searchQuery.trim().length > 0;
    if (searchActive) {
      // Search shows every matching project — maturity filter not applied.
      result = result.filter((p) => projectMatchesSearch(p, searchQuery));
    } else {
      // Maturity filter: applied only when showAllProjects is false (user opted into mature-only view).
      result = filterMatureProjects(result, timelineEventCounts, showAllProjects);
    }
    // 置顶项目按 PRIORITY_PROJECT_NAMES 顺序排最前；其余项目按机会评分
    // 降序，同分按名称升序，评分异常/不可得沉底（噪音项目自然沉底）。
    const pinnedFirst = sortPriorityFirst(result, (p) => priorityProjectRankByName(p.name));
    const pinned = pinnedFirst.filter((p) => priorityProjectRankByName(p.name) >= 0);
    const rest = pinnedFirst.filter((p) => priorityProjectRankByName(p.name) < 0);
    // 每个项目只评分一次；评分异常/不可得记 -1 沉底。
    const restScores = new Map<Project, number>();
    for (const p of rest) {
      try {
        restScores.set(p, scoreOpportunity(p).totalScore);
      } catch {
        restScores.set(p, -1);
      }
    }
    rest.sort((a, b) => {
      const diff = (restScores.get(b) ?? -1) - (restScores.get(a) ?? -1);
      return diff !== 0 ? diff : a.name.localeCompare(b.name);
    });
    return [...pinned, ...rest];
  }, [projects, selectedCountry, selectedIndustry, selectedConfidence, selectedPhases, timelineEventCounts, showAllProjects, searchQuery]);

  const filteredStats = useMemo(() => getStats(filteredProjects), [filteredProjects]);

  // 图表数据
  const countryChartData = useMemo(() => {
    const count: Record<string, number> = {};
    for (const p of filteredProjects) {
      const c = p.country.trim();
      count[c] = (count[c] ?? 0) + 1;
    }
    const entries = Object.entries(count)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
    // 最多 6 个国家 + Other：小国合并，保持环形图可读
    if (entries.length <= 7) return entries;
    const top = entries.slice(0, 6);
    const otherValue = entries.slice(6).reduce((sum, e) => sum + e.value, 0);
    return [...top, { name: "Other", value: otherValue }];
  }, [filteredProjects]);

  const countryTotal = useMemo(
    () => countryChartData.reduce((sum, d) => sum + d.value, 0),
    [countryChartData],
  );

  const phaseChartData = useMemo(() => {
    const count: Record<string, number> = {};
    for (const p of filteredProjects) {
      const ph = phaseLabel(p.phase);
      count[ph] = (count[ph] ?? 0) + 1;
    }
    // 9 phases in lifecycle order, then Unknown last
    const order = [...PHASES, PHASE_UNKNOWN];
    return order
      .filter((ph) => count[ph] != null)
      .map((ph) => ({ name: ph, value: count[ph] }));
  }, [filteredProjects]);

  const phaseBarMax = useMemo(
    () => Math.max(...phaseChartData.map((d) => d.value), 1),
    [phaseChartData],
  );

  // 地图光点 — 始终基于全部项目（不受筛选影响），点击光点仍会联动下拉框筛选
  const allCountries = useMemo(
    () => getUniqueCountries(projects),
    [projects],
  );

  const mapDots = useMemo(() => {
    const mapped = allCountries.filter((c) => countryCoordinates[c]);
    mapped.sort((a, b) => countryCoordinates[b].x - countryCoordinates[a].x);
    return mapped.map((country, index) => ({
      country,
      x: countryCoordinates[country].x,
      y: countryCoordinates[country].y,
      delay: `${index * 0.2}s`,
    }));
  }, [allCountries]);

  // 诊断日志: 打印有光点 / 缺失坐标的国家
  useEffect(() => {
    if (loading) return;
    const withDots = allCountries.filter((c) => countryCoordinates[c]);
    const withoutDots = allCountries.filter((c) => !countryCoordinates[c]);
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
  }, [allCountries, loading]);

  // ---- 获取项目时间线事件 ----
  useEffect(() => {
    if (!selectedProject) {
      setTimelineEvents([]);
      return;
    }
    const projectName = selectedProject.name;
    const canonicalId = normalizeProjectName(projectName);

    let cancelled = false;
    setTimelineLoading(true);


    async function fetchTimeline() {
      let data: Record<string, unknown>[] | null = null;
      let error: { message: string } | null = null;

      if (canonicalId) {
        // Primary path: query by canonical_project_id
        const result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .eq("canonical_project_id", canonicalId)
          .order("publication_date", { ascending: true });
        data = result.data;
        error = result.error;

        // Fallback: canonical ID known but no events linked to it yet —
        // events may exist under a raw project name that has not been
        // backfilled into canonical_project_id. Try name fuzzy match.
        if (!error && (!data || data.length === 0)) {
          const candidates = fuzzyCandidates(projectName);
          for (const name of candidates) {
            const result2 = await supabase
              .from("candidate_events")
              .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
              .ilike("project_name_raw", `%${name}%`)
              .order("publication_date", { ascending: true });
            if (!result2.error && result2.data && result2.data.length > 0) {
              data = result2.data;
              error = result2.error;
              break;
            }
            data = result2.data;
            error = result2.error;
          }
        }
      } else {
        // Fallback: query by project_name_raw (fuzzy match) when no canonical ID
        // Handles projects promoted from NSTA fields, news headlines, etc.
        // that are not in the PROJECT_ALIASES registry.
        const candidates = fuzzyCandidates(projectName);
        let result: { data: Record<string, unknown>[] | null; error: { message: string } | null } | null = null;
        for (const name of candidates) {
          const r = await supabase
            .from("candidate_events")
            .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
            .ilike("project_name_raw", `%${name}%`)
            .order("publication_date", { ascending: true });
          if (!r.error && r.data && r.data.length > 0) {
            result = r;
            break;
          }
          result = r;
        }
        data = result?.data ?? null;
        error = result?.error ?? null;
      }

      if (cancelled) return;

      if (error) {
        console.error("[Timeline] Fetch failed:", error.message);
        setTimelineEvents([]);
      } else {
        const events: TimelineEvent[] = (data ?? []).map((row: Record<string, unknown>) => ({
          id: Number(row.id),
          eventType: String(row.event_type ?? ""),
          publicationDate: String(row.publication_date ?? ""),
          sourceName: String(row.source_name ?? ""),
          sourceUrl: String(row.source_url ?? ""),
          evidenceQuote: String(row.evidence_quote ?? ""),
          summary: String(row.summary ?? ""),
        }));
        setTimelineEvents(events);
      }
      setTimelineLoading(false);
    }

    fetchTimeline();

    return () => { cancelled = true; };
  }, [selectedProject]);

  /** Short timeline digest for the battle card — undefined until events load. */
  const battleTimelineSummary = useMemo(() => {
    if (timelineEvents.length === 0) return undefined;
    const head = timelineEvents
      .slice(0, 3)
      .map((e) => `${formatEventType(e.eventType)}${e.publicationDate ? ` ${e.publicationDate.slice(0, 4)}` : ""}`)
      .join(" · ");
    return `${head}（共 ${timelineEvents.length} 条）`;
  }, [timelineEvents]);

  // ---- AI 分析（LLM 可用时返回 AI 结果，否则 fallback 到规则引擎）----
  /** Name candidates for fuzzy timeline matching: core name (text before
   * the first parenthesis) first, then the full name. Raw rows usually
   * store just the field name ("TERN"), not the display suffix
   * ("SKUA (Part of MARNOCK-SKUA)"). */
  function fuzzyCandidates(projectName: string): string[] {
    const core = projectName.split("(")[0].trim().replace(/\)$/, "");
    return [core, projectName]
      .filter((n, i, arr) => n.length >= 3 && arr.indexOf(n) === i)
      .map((n) => n.slice(0, 60));
  }

  useEffect(() => {
    if (!selectedProject) {
      setAiScenario(null);
      setAiAssessment(null);
      return;
    }
    let cancelled = false;
    setAiScenario(null);
    setAiAssessment(null);
    Promise.all([
      analyzeProjectScenario(selectedProject),
      assessOpportunity(selectedProject),
    ]).then(([scenario, assessment]) => {
      if (cancelled) return;
      setAiScenario(scenario);
      setAiAssessment(assessment);
    });
    return () => { cancelled = true; };
  }, [selectedProject]);

  const handleDotClick = (country: string) => {
    setSelectedCountry(country);
    console.log(`Dot clicked: ${country} (${projects.filter((p) => p.country.trim() === country).length} projects)`);
  };

  function handleIndustryChange(value: string) {
    setSelectedIndustry(value);
  }

  function togglePhase(phase: string) {
    setSelectedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phase)) next.delete(phase);
      else next.add(phase);
      return next;
    });
  }

  function clearAllFilters() {
    setSelectedCountry("All Countries");
    setSelectedIndustry("All Industries");
    setSelectedConfidence("High & Medium");
    setSelectedPhases(new Set([...PHASES, PHASE_UNKNOWN]));
  }

  /** Handle CSV export of factory-qualified projects in current view. */
  function handleExport() {
    if (!requireLogin()) return;
    void exportOpportunityList(filteredProjects, window.location.origin);
  }

  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <>
      <PageMeta title="Business Opportunity Discovery" description="全球 FPSO 项目不锈钢商机挖掘系统" />

      <Header rightContent={
        <div className="flex flex-shrink-0 items-center gap-2">
          <GlobalSearch
            projects={projects}
            value={searchQuery}
            onChange={setSearchQuery}
            onSelect={(p) => setSelectedProject(p)}
          />
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

      <div className="max-w-7xl mx-auto">
        <FilterSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          countries={countries}
          projects={projects}
          selectedCountry={selectedCountry}
          selectedIndustry={selectedIndustry}
          selectedConfidence={selectedConfidence}
          selectedPhases={selectedPhases}
          onCountryChange={setSelectedCountry}
          onIndustryChange={handleIndustryChange}
          onConfidenceChange={setSelectedConfidence}
          onPhaseToggle={togglePhase}
          onClear={clearAllFilters}
          onExport={handleExport}
          filteredCount={filteredProjects.length}
          showAllProjects={showAllProjects}
          onShowAllProjectsChange={setShowAllProjects}
        />

        <main
          className="flex-1 min-w-0 px-6 py-10 transition-all duration-300 ease-in-out max-md:!ml-0"
          style={{ marginLeft: sidebarCollapsed ? 48 : 260 }}
        >
        {/* 页面标题 */}
        <section className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
            全球 FPSO 项目商机挖掘
          </h1>
        </section>

        {/* 指标统计带 */}
        <section className="mb-8">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {/* Total Projects */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-blue/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(0,212,255,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <Building2 className="h-20 w-20 text-fpso-blue" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-blue/10 ring-1 ring-fpso-blue/20">
                  <Building2 className="h-4 w-4 text-fpso-blue" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Total Projects</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.total}</div>
                </div>
              </div>
            </div>

            {/* Early (Concept / Planning / Design) */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-muted/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(148,163,184,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <CalendarDays className="h-20 w-20 text-fpso-muted" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-muted/10 ring-1 ring-fpso-muted/20">
                  <CalendarDays className="h-4 w-4 text-fpso-muted" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Early Phase</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.early}</div>
                  <div className="truncate text-xs text-fpso-dim">Concept · Planning · Design</div>
                </div>
              </div>
            </div>

            {/* Mid (Approval / EPC Award / Procurement) */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-yellow-400/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(250,204,21,0.08)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <Hammer className="h-20 w-20 text-yellow-400" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-yellow-400/10 ring-1 ring-yellow-400/20">
                  <Hammer className="h-4 w-4 text-yellow-400" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Mid Phase</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.mid}</div>
                  <div className="truncate text-xs text-fpso-dim">Approval · EPC Award · Procurement</div>
                </div>
              </div>
            </div>

            {/* Late (Construction / Commissioning / Delivery) */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-blue/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(0,212,255,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <Hammer className="h-20 w-20 text-fpso-blue" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-blue/10 ring-1 ring-fpso-blue/20">
                  <Hammer className="h-4 w-4 text-fpso-blue" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Late Phase</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.late}</div>
                  <div className="truncate text-xs text-fpso-dim">Construction · Commissioning · Delivery</div>
                </div>
              </div>
            </div>

            {/* Added This Week */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-green/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(16,185,129,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <PlusCircle className="h-20 w-20 text-fpso-green" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-green/10 ring-1 ring-fpso-green/20">
                  <PlusCircle className="h-4 w-4 text-fpso-green" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Added This Week</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.addedThisWeek}</div>
                  <div className="truncate text-xs text-fpso-dim">New Discoveries</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 全球分布地图 */}
        <section className="mb-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-medium text-fpso-fg">全球分布</h2>
            <span className="text-xs text-fpso-muted">Equirectangular Projection</span>
          </div>

          <div className="map-container relative w-full overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300">
            <img
              src="/world-map.png"
              alt="世界地图轮廓"
              className="pointer-events-none absolute inset-0 z-0 h-auto w-full select-none"
              style={{ filter: "brightness(2.0) contrast(1.4)" }}
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
                  className="map-pulse absolute z-10 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border border-fpso-blue bg-fpso-blue outline-none focus:ring-2 focus:ring-fpso-blue/50"
                  style={{
                    left: `${dot.x}%`,
                    top: `${dot.y}%`,
                    animationDelay: dot.delay,
                    "--dot-delay": dot.delay,
                  } as React.CSSProperties}
                  aria-label={`${dot.country} 项目`}
                />
              ))
            )}
          </div>

        </section>

        {/* 图表区域 */}
        <section className="mb-10 grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2">
          {/* 国家分布环形图 */}
          <div className="group relative flex flex-col overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md p-5 shadow-xl transition-all duration-300 hover:border-fpso-blue/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(0,212,255,0.06)]">
            <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
              <Globe className="h-20 w-20 text-fpso-blue" />
            </div>
            <div className="relative z-10 flex flex-1 flex-col">
              <h3 className="mb-4 border-b border-white/5 pb-3 text-xs font-semibold uppercase tracking-widest text-fpso-muted">Country Distribution</h3>
              {countryChartData.length === 0 ? (
                <div className="flex flex-1 items-center justify-center">
                  <span className="text-sm text-fpso-muted">No country data for current filters.</span>
                </div>
              ) : (
                <>
                  <div className="relative h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={countryChartData}
                          cx="50%"
                          cy="50%"
                          innerRadius={62}
                          outerRadius={88}
                          paddingAngle={2}
                          dataKey="value"
                          stroke="transparent"
                        >
                          {countryChartData.map((d, i) => (
                            <Cell
                              key={d.name}
                              fill={COUNTRY_CHART_COLORS[i]}
                              className={d.name === "Other" ? "chart-slice chart-slice--static" : "chart-slice"}
                              onClick={() => {
                                if (d.name !== "Other") setSelectedCountry(d.name);
                              }}
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
                          formatter={(value: number, name: string) => [`${value} projects`, name]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    {/* 中心总数 */}
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                      <div
                        className="font-mono text-3xl font-extrabold tabular-nums text-fpso-fg"
                        style={{ textShadow: "0 0 12px rgba(0,212,255,0.5)" }}
                      >
                        {countryTotal}
                      </div>
                      <div className="text-xs text-fpso-muted">Projects</div>
                    </div>
                  </div>
                  {/* 图例：色点 + 国旗 + 国家 + 数值 + 百分比，点击联动筛选 */}
                  <div className="mt-4 space-y-1">
                    {countryChartData.map((d, i) => {
                      const flag = d.name === "Other" ? "🌐" : countryToFlagEmoji(d.name) || "🌐";
                      const pct = countryTotal > 0 ? Math.round((d.value / countryTotal) * 100) : 0;
                      return (
                        <button
                          key={d.name}
                          type="button"
                          disabled={d.name === "Other"}
                          onClick={() => setSelectedCountry(d.name)}
                          className="flex w-full items-center gap-2.5 rounded-md px-1.5 py-1 text-left text-xs transition-colors hover:bg-fpso-blue/[0.04] disabled:cursor-default"
                        >
                          <span
                            className="h-2 w-2 flex-shrink-0 rounded-full"
                            style={{ background: COUNTRY_CHART_COLORS[i] }}
                          />
                          <span className="flex-shrink-0 text-sm leading-none">{flag}</span>
                          <span className="min-w-0 flex-1 truncate text-fpso-muted">{d.name}</span>
                          <span className="font-mono tabular-nums text-fpso-fg">{d.value}</span>
                          <span className="w-10 flex-shrink-0 text-right font-mono tabular-nums text-fpso-dim">{pct}%</span>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* 状态分布水平条形图 */}
          <div className="group relative flex flex-col overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md p-5 shadow-xl transition-all duration-300 hover:border-fpso-blue/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(0,212,255,0.06)]">
            <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
              <BarChart3 className="h-20 w-20 text-fpso-blue" />
            </div>
            <div className="relative z-10 flex flex-1 flex-col">
              <h3 className="mb-4 border-b border-white/5 pb-3 text-xs font-semibold uppercase tracking-widest text-fpso-muted">Phase Breakdown</h3>
              {phaseChartData.length === 0 ? (
                <div className="flex flex-1 items-center justify-center">
                  <span className="text-sm text-fpso-muted">No phase data for current filters.</span>
                </div>
              ) : (
                <div className="flex flex-1 flex-col justify-center gap-4">
                  {phaseChartData.map((d) => {
                    const color = PHASE_HEX[d.name] ?? "#64748b";
                    const widthPct = Math.max(Math.round((d.value / phaseBarMax) * 100), 2);
                    return (
                      <div key={d.name} className="group/row relative">
                        <div className="flex items-center gap-3">
                          <span className="flex w-36 flex-shrink-0 items-center gap-2 text-xs text-fpso-muted">
                            <span
                              className="h-2 w-2 flex-shrink-0 rounded-full"
                              style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                            />
                            <span className="truncate">{d.name}</span>
                          </span>
                          <div className="h-3 flex-1 overflow-hidden rounded-full bg-[#1e2844]">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${widthPct}%` }}
                              transition={{ duration: 0.6, ease: "easeOut" }}
                              className="h-full rounded-full transition-all duration-200 group-hover/row:brightness-125"
                              style={{
                                background: `linear-gradient(90deg, ${color}55, ${color})`,
                                boxShadow: `0 0 8px ${color}66`,
                              }}
                            />
                          </div>
                          <span className="w-10 flex-shrink-0 text-right font-mono text-xs tabular-nums text-fpso-fg">
                            {d.value}
                          </span>
                        </div>
                        {/* hover tooltip：状态名 + 数量 */}
                        <div className="pointer-events-none absolute -top-8 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md border border-[#1e2844] bg-[#131a2e] px-2.5 py-1 text-xs text-fpso-fg opacity-0 shadow-xl transition-opacity duration-200 group-hover/row:opacity-100">
                          {d.name} — {d.value} projects
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
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

          <div className="rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300">
            {loading ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">Loading projects…</div>
            ) : filteredProjects.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">
                No projects found for the selected industry and country.
              </div>
            ) : (
              filteredProjects.map((project) => (
                <DashboardProjectCard
                  key={project.name}
                  project={project}
                  onOpen={setSelectedProject}
                  milestoneMap={milestoneMap}
                  timelineEventCounts={timelineEventCounts}
                  showAllProjects={showAllProjects}
                />
              ))
            )}
          </div>
        </section>
      </main>
      </div>

      {/* 页脚 */}
      <footer className="mt-auto border-t border-white/5 bg-fpso-bg">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-6 py-5 md:flex-row">
          <span className="text-xs text-fpso-dim">
            Data aggregated from public sources. For internal analysis only.
          </span>
          <span className="text-xs text-fpso-dim">Last updated: {todayStr}</span>
        </div>
      </footer>

      {/* 项目详情模态框 */}
      {selectedProject && (() => {
        const specs = {
          waterDepthM: selectedProject.waterDepthM,
          oilCapacityBpd: selectedProject.oilCapacityBpd,
          gasCapacityMmcmd: selectedProject.gasCapacityMmcmd,
          hullType: selectedProject.hullType,
          fieldName: selectedProject.fieldName,
          operatorName: selectedProject.operatorName,
          basin: selectedProject.basin,
        };
        const showSpecs = hasAnySpecs(specs);

        return (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => { setSelectedProject(null); setModalTab("overview"); }}
        >
          {/* 遮罩层 */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />

          {/* 模态框本体 */}
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative z-10 w-full max-w-lg max-h-[85vh] flex flex-col rounded-xl border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-2xl animate-fade-in"
          >
            {/* 顶部栏 */}
            <div className="flex-shrink-0 flex items-center justify-between border-b border-white/5 px-6 py-4">
              <h2 className="text-base font-semibold text-fpso-fg">Project Detail</h2>
              <button
                onClick={() => { setSelectedProject(null); setModalTab("overview"); }}
                className="rounded-md p-1.5 text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg"
                aria-label="Close"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tab 导航 —— Overview / Timeline */}
            <div className="flex-shrink-0 flex border-b border-white/5 px-6">
                <button
                  type="button"
                  onClick={() => setModalTab("overview")}
                  className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
                    modalTab === "overview"
                      ? "text-fpso-blue"
                      : "text-fpso-muted hover:text-fpso-fg"
                  }`}
                >
                  Overview
                  {modalTab === "overview" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-fpso-blue" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setModalTab("timeline")}
                  className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
                    modalTab === "timeline"
                      ? "text-fpso-blue"
                      : "text-fpso-muted hover:text-fpso-fg"
                  }`}
                >
                  Timeline
                  {modalTab === "timeline" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-fpso-blue" />
                  )}
                </button>
            </div>

            {/* ---- Overview 内容 ---- */}
            {modalTab === "overview" && (
            <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-5">
              {/* 项目名称 */}
              <h3 className="text-xl font-bold text-fpso-fg">{selectedProject.name}</h3>

              {/* 国家与状态 */}
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1.5 rounded-md bg-fpso-bg px-3 py-1 text-sm text-fpso-fg">
                  {selectedProject.flag && <span>{selectedProject.flag}</span>}
                  <span>{selectedProject.country}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-md bg-fpso-bg px-3 py-1 text-sm">
                  <span className={`h-2 w-2 rounded-full ${phaseDotClass(selectedProject.phase)}`} style={{ boxShadow: `0 0 6px currentColor` }} />
                  <span className={phaseColorClass(selectedProject.phase)}>{phaseLabel(selectedProject.phase)}</span>
                </span>
                {selectedProject.confidence && (
                  <span className={`inline-flex items-center gap-1 rounded-md px-3 py-1 text-sm ${confidenceBadgeClass(selectedProject.confidence)}`}>
                    {selectedProject.confidence}
                  </span>
                )}
              </div>

              {/* follow / unfollow button — login required on click */}
              <div>
                <Button
                  variant={isFollowing(selectedProject.name) ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    if (!requireLogin()) return;
                    toggleFollowProject(selectedProject.name);
                  }}
                  className={
                    isFollowing(selectedProject.name)
                      ? 'bg-fpso-blue hover:bg-fpso-blue/80 text-white text-xs'
                      : 'border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-xs'
                  }
                >
                  {isFollowing(selectedProject.name) ? '★ Following' : '☆ Follow'}
                </Button>
              </div>

              {/* Follow-up Status (S7) */}
              <div className="mb-5">
                <FollowUpStatus
                  projectId={selectedProject.name}
                  projectName={selectedProject.name}
                />
              </div>

              {/* 完整摘要 */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Summary</h4>
                <p className="text-sm leading-relaxed text-fpso-fg">
                  {selectedProject.summary || <span className="text-fpso-dim italic">暂无数据</span>}
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
                  ) : (
                    <span className="text-fpso-dim italic">暂无数据</span>
                  )}
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
                  ) : (
                    <span className="text-fpso-dim italic">暂无数据</span>
                  )}
                </p>
              </div>

              {/* 采购链 — always visible, missing data marked instead of hidden */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-fpso-dim">Procurement Chain</h4>
                {selectedProject.procurementChain ? (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedProject.procurementChain.split(/,\s*/).filter(Boolean).map((entity) => (
                      <span key={entity} className="rounded bg-fpso-green/10 px-2 py-0.5 text-xs font-medium text-fpso-green">
                        {entity}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-fpso-dim italic">暂无数据</span>
                )}
              </div>

              {/* Technical Specs & Material Matching — always visible, missing data marked */}
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
                  Technical Specs &amp; Material Matching
                </h4>
                {(() => {
                  if (!showSpecs) return null;
                  return (
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
                                const cmTags = getCorrosiveMediaTags(selectedProject.corrosiveMedia);
                                const cmDetails = getCorrosiveMediaDetails(selectedProject.corrosiveMedia);
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
                  );
                })()}
                  <div className="mt-2">
                    {/* AI 个性化分析（同飞书推送）— 每条推荐附理由，规则兜底 */}
                    <PushAnalysisPanel analysis={pushAnalysis} />
                  </div>
              </div>

              {/* Opportunity Score (S5) */}
              {(() => {
                const scoreResult = scoreOpportunity(selectedProject);
                return (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
                      Opportunity Score
                    </h4>
                    {/* Progress bar */}
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
                    {/* Summary */}
                    <p className="text-xs text-fpso-muted mb-2">{scoreResult.summary}</p>
                    <p className="text-xs text-fpso-fg mb-3">
                      <span className="font-semibold text-fpso-blue">Action: </span>
                      {scoreResult.recommendedAction}
                    </p>
                    {/* AI 采购时间窗推理依据 — AI 成功时在评分区下展示引用块 */}
                    {pushAnalysis?.source === "ai" && pushAnalysis.procurement_window.reasoning && (
                      <div className="mb-3">
                        <div className="mb-1 flex items-center gap-2">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
                            采购时间窗推理依据
                          </span>
                          <PushSourceBadge source="ai" />
                        </div>
                        <blockquote className="border-l-2 border-fpso-green/40 pl-3 text-xs leading-relaxed text-fpso-green/80 italic">
                          {pushAnalysis.procurement_window.reasoning}
                        </blockquote>
                      </div>
                    )}
                    {/* AI 机会判断（仅 AI 成功时展示，规则结果已在上方展示） */}
                    {aiAssessment?.source === "ai" && (
                      <div className="mb-3 rounded-md border border-fpso-green/15 bg-fpso-green/[0.05] p-2.5">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
                            AI 机会判断
                          </span>
                          <SourceBadge source="ai" />
                        </div>
                        <p className="text-xs leading-relaxed text-fpso-fg/90">{aiAssessment.data.verdict}</p>
                        {aiAssessment.data.rationale && (
                          <p className="mt-1 text-[11px] leading-relaxed text-fpso-green/80">{aiAssessment.data.rationale}</p>
                        )}
                      </div>
                    )}
                    {/* Battle Card + Outreach buttons */}
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setBattleCardProject(selectedProject)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-fpso-green/20 bg-fpso-green/5 px-3 py-1.5 text-xs font-medium text-fpso-green hover:bg-fpso-green/10 hover:border-fpso-green/30 transition-colors"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          生成作战卡
                        </button>

                        <button
                          type="button"
                          onClick={() => setOutreachProject(selectedProject)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-fpso-orange/20 bg-fpso-orange/5 px-3 py-1.5 text-xs font-medium text-fpso-orange hover:bg-fpso-orange/10 hover:border-fpso-orange/30 transition-colors"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                          </svg>
                          生成开发信
                        </button>
                      </div>
                    {/* Expandable dimensions via native <details> */}
                    <details className="group">
                      <summary className="text-xs font-medium text-fpso-blue hover:text-fpso-blue/80 transition-colors cursor-pointer select-none mb-2">
                        Show dimension details
                      </summary>
                      <div className="space-y-2 pl-2 border-l-2 border-fpso-blue/20">
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
                  </div>
                );
              })()}

              {/* AI 分析（S8）— LLM 不可用时展示规则引擎 fallback 并标注来源 */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-fpso-dim">AI 分析</h4>
                  {aiScenario && <SourceBadge source={aiScenario.source} />}
                </div>
                {!aiScenario ? (
                  <p className="text-xs italic text-fpso-dim">AI 分析中…</p>
                ) : (
                  <div className="space-y-2 rounded-md border border-fpso-blue/10 bg-fpso-blue/[0.04] p-3">
                    <p className="text-xs leading-relaxed text-fpso-fg/90">{aiScenario.data.scenario}</p>
                    {aiScenario.data.keyPoints.length > 0 && (
                      <ul className="space-y-1">
                        {aiScenario.data.keyPoints.map((k) => (
                          <li key={k} className="text-[11px] leading-relaxed text-fpso-blue/80">• {k}</li>
                        ))}
                      </ul>
                    )}
                    {aiScenario.data.risks.length > 0 && (
                      <ul className="space-y-1">
                        {aiScenario.data.risks.map((r) => (
                          <li key={r} className="text-[11px] leading-relaxed text-fpso-orange/80">⚠ {r}</li>
                        ))}
                      </ul>
                    )}
                    {aiScenario.data.infoGaps.length > 0 && (
                      <ul className="space-y-1">
                        {aiScenario.data.infoGaps.map((g) => (
                          <li key={g} className="text-[11px] leading-relaxed text-fpso-muted/80">∅ {g}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

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
            )}

            {/* ---- Timeline 内容 ---- */}
            {modalTab === "timeline" && (
            <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5">
              {timelineLoading ? (
                <div className="flex items-center justify-center py-10">
                  <span className="text-sm text-fpso-muted">Loading timeline…</span>
                </div>
              ) : timelineEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-fpso-dim mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-sm text-fpso-muted">该项目的关键事件较少，系统正在持续挖掘中</p>
                  <p className="text-xs text-fpso-dim mt-1">
                    待后续抓取到技术参数与时间线事件后，将自动升级为成熟商机。
                  </p>
                </div>
              ) : (
                <div className="relative">
                  {/* 竖线 */}
                  <div className="absolute left-[11px] top-1 bottom-1 w-0.5 bg-fpso-border" />
                  <div className="space-y-4">
                    {timelineEvents.map((evt) => (
                      <div key={evt.id} className="relative flex gap-4">
                        {/* 圆点 */}
                        <div className={`relative z-10 mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full border-2 border-fpso-card ${timelineDotColor(evt.eventType)}`} />
                        {/* 内容卡片 */}
                        <div className="flex-1 min-w-0 rounded-md border border-white/5 bg-fpso-bg/40 backdrop-blur-md px-3 py-2.5">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-xs font-semibold text-fpso-fg">
                              {formatEventType(evt.eventType)}
                            </span>
                            <span className="text-[10px] text-fpso-dim font-mono flex-shrink-0">
                              {evt.publicationDate || "—"}
                            </span>
                          </div>
                          {evt.summary && (
                            <p className="text-xs text-fpso-fg/80 leading-relaxed mb-1.5">
                              {evt.summary}
                            </p>
                          )}
                          {evt.evidenceQuote && (
                            <blockquote className="border-l-2 border-fpso-blue/30 pl-2.5 text-[11px] text-fpso-muted italic leading-relaxed mb-1.5">
                              &ldquo;{evt.evidenceQuote}&rdquo;
                            </blockquote>
                          )}
                          <div className="flex items-center gap-1.5">
                            {evt.sourceUrl ? (
                              <a
                                href={evt.sourceUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[10px] text-fpso-blue hover:underline inline-flex items-center gap-0.5"
                              >
                                {evt.sourceName || evt.sourceUrl}
                                <span className="text-[0.8em]">↗</span>
                              </a>
                            ) : (
                              <span className="text-[10px] text-fpso-dim">{evt.sourceName || "—"}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Link to full timeline page */}
              <div className="mt-5 pt-3 border-t border-white/5 text-center">
                  <button
                    type="button"
                    onClick={() => {
                      const canonicalId = normalizeProjectName(selectedProject.name);
                      const params = new URLSearchParams();
                      if (canonicalId) {
                        params.set("project", canonicalId);
                      } else {
                        // Fallback: pass raw project name for unmatched projects
                        params.set("projectName", selectedProject.name);
                      }
                      setSelectedProject(null);
                      setModalTab("overview");
                      navigate(`/project-timeline?${params.toString()}`);
                    }}
                    className="text-xs text-fpso-blue/70 hover:text-fpso-blue transition-colors inline-flex items-center gap-1"
                  >
                    查看完整时间线 <span className="text-[0.8em]">→</span>
                  </button>
              </div>
            </div>
            )}
          </div>
        </div>
        );
      })()}

      {/* 作战卡弹窗 */}
      {battleCardProject && (
        <div
          className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[5vh]"
          onClick={() => setBattleCardProject(null)}
        >
          {/* 遮罩层 */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />

          {/* 作战卡容器 */}
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative z-10 w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-fade-in"
          >
            {/* 关闭按钮 */}
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
              timelineSummary={battleTimelineSummary}
            />
          </div>
        </div>
      )}

      {/* 开发信弹窗 */}
      <OutreachModal project={outreachProject} onClose={() => setOutreachProject(null)} />
    </>
  );
}
