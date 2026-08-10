/**
 * Business Opportunity Discovery
 * 深色数据终端风格单页面：全球 FPSO 项目不锈钢商机挖掘系统
 * 数据源：Supabase projects + candidate_events 合并显示
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis,
} from "recharts";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project, MaterialMatchResult } from "@/data/projects";
import { countryCoordinates, sampleProjects, countryToFlagEmoji, COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { useSubscription } from "@/hooks/useSubscription";
import { matchMaterials, specsFromRow, hasAnySpecs, parseRecommendation, parseCorrosiveMedia, getCorrosiveMediaTags, getCorrosiveMediaDetails } from "@/lib/material_matcher";
import { exportOpportunityList } from "@/lib/export_opportunities";
import { Building2, Hammer, CalendarDays, PlusCircle, Anchor, Waves, Gauge } from "lucide-react";
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
  active: number;
  planned: number;
  addedThisWeek: number;
}

function getStats(projects: Project[]): Stats {
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  return {
    total: projects.length,
    active: projects.filter((p) => p.status === "Under Construction").length,
    planned: projects.filter((p) => p.status === "Planned").length,
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

function statusBorderLClass(status: string): string {
  switch (status) {
    case "Under Construction":
      return "border-l-fpso-blue";
    case "Delivered":
      return "border-l-fpso-green";
    case "Planned":
      return "border-l-fpso-orange";
    default:
      return "border-l-fpso-muted";
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

/** Phase segments for the progress bar: label, lit color, unlit color. */
const PHASE_SEGMENTS = [
  { label: "规划", color: "#6b7280" },
  { label: "FEED", color: "#7dd3fc" },
  { label: "在建", color: "#00d4ff" },
  { label: "投产", color: "#10b981" },
] as const;

const PHASE_UNLIT = "#1e2844";

/** Map project status to phase progress (0-4 segments lit).
 *  0 = none, 1 = 规划, 2 = FEED, 3 = 在建, 4 = 投产.
 *  Derived from milestone data when available; falls back to status inference. */
function getPhaseProgress(status: string): number {
  switch (status) {
    case "Planned":
      return 1;
    case "Under Construction":
      return 3;
    case "Delivered":
      return 4;
    default:
      return 0;
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

export default function DashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCountry, setSelectedCountry] = useState("All Countries");
  const [selectedIndustry, setSelectedIndustry] = useState("All Industries");
  const [selectedConfidence, setSelectedConfidence] = useState("All");
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(
    new Set(["Under Construction", "Planned"]),
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [milestoneMap, setMilestoneMap] = useState<Map<string, { label: string; year: string }>>(new Map());
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [modalTab, setModalTab] = useState<"overview" | "timeline">("overview");
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const { version, status: connectionStatus } = useProjectRealtime();
  const { isFollowing, toggleFollowProject, isAuthenticated } = useSubscription();

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

  // ---- Fetch milestone data for next-milestone preview ----
  useEffect(() => {
    let cancelled = false;

    async function fetchMilestones() {
      const { data, error } = await supabase
        .from("candidate_events")
        .select("canonical_project_id, event_type, publication_date")
        .not("canonical_project_id", "is", null);

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
    if (selectedConfidence !== "All") {
      result = result.filter(
        (p) => (p.confidence ?? "medium") === selectedConfidence.toLowerCase(),
      );
    }
    if (selectedStatuses.size > 0) {
      result = result.filter((p) => selectedStatuses.has(p.status || "Unknown"));
    }
    return result;
  }, [projects, selectedCountry, selectedIndustry, selectedConfidence, selectedStatuses]);

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

  // ---- 获取项目时间线事件 ----
  useEffect(() => {
    if (!selectedProject) {
      setTimelineEvents([]);
      return;
    }
    const industry = selectedProject.industry ?? "FPSO";
    if (industry !== "FPSO") {
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
      } else {
        // Fallback: query by project_name_raw (fuzzy match) when no canonical ID
        // Handles projects promoted from NSTA fields, news headlines, etc.
        // that are not in the PROJECT_ALIASES registry.
        const result = await supabase
          .from("candidate_events")
          .select("id, event_type, publication_date, source_name, source_url, evidence_quote, summary")
          .ilike("project_name_raw", `%${projectName.slice(0, 40)}%`)
          .order("publication_date", { ascending: true });
        data = result.data;
        error = result.error;
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

  const handleDotClick = (country: string) => {
    setSelectedCountry(country);
    console.log(`Dot clicked: ${country} (${projects.filter((p) => p.country.trim() === country).length} projects)`);
  };

  function handleIndustryChange(value: string) {
    setSelectedIndustry(value);
    if (value !== "All Industries") {
      navigate(`/database?industry=${encodeURIComponent(value)}`);
    }
  }

  function toggleStatus(status: string) {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }

  function clearAllFilters() {
    setSelectedCountry("All Countries");
    setSelectedIndustry("All Industries");
    setSelectedConfidence("All");
    setSelectedStatuses(new Set(["Under Construction", "Planned"]));
  }

  /** Handle CSV export of factory-qualified projects in current view. */
  function handleExport() {
    exportOpportunityList(filteredProjects, window.location.origin);
  }

  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <>
      <PageMeta title="Business Opportunity Discovery" description="全球 FPSO 项目不锈钢商机挖掘系统" />

      <Header rightContent={
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
      } />

      <div className="flex max-w-7xl mx-auto">
        <FilterSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          countries={countries}
          projects={projects}
          selectedCountry={selectedCountry}
          selectedIndustry={selectedIndustry}
          selectedConfidence={selectedConfidence}
          selectedStatuses={selectedStatuses}
          onCountryChange={setSelectedCountry}
          onIndustryChange={handleIndustryChange}
          onConfidenceChange={setSelectedConfidence}
          onStatusToggle={toggleStatus}
          onClear={clearAllFilters}
          onExport={handleExport}
          filteredCount={filteredProjects.length}
        />

        <main className="flex-1 min-w-0 px-6 py-10">
        {/* 页面标题 */}
        <section className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
            全球 FPSO 项目商机挖掘
          </h1>
        </section>

        {/* 指标统计带 */}
        <section className="mb-8">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
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

            {/* Active (Under Construction) */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-blue/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(0,212,255,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <Hammer className="h-20 w-20 text-fpso-blue" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-blue/10 ring-1 ring-fpso-blue/20">
                  <Hammer className="h-4 w-4 text-fpso-blue" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Active</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.active}</div>
                  <div className="truncate text-xs text-fpso-dim">Under Construction</div>
                </div>
              </div>
            </div>

            {/* Planned */}
            <div className="group relative overflow-hidden rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300 p-4 transition-all hover:border-fpso-orange/40 hover:bg-fpso-card/60 hover:shadow-[0_0_20px_rgba(255,159,67,0.06)]">
              <div className="absolute -right-2 -top-3 opacity-[0.05] transition-opacity group-hover:opacity-[0.09]">
                <CalendarDays className="h-20 w-20 text-fpso-orange" />
              </div>
              <div className="relative z-10 flex items-center gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-fpso-orange/10 ring-1 ring-fpso-orange/20">
                  <CalendarDays className="h-4 w-4 text-fpso-orange" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold uppercase tracking-widest text-fpso-muted">Planned</div>
                  <div className="font-mono text-4xl font-extrabold text-fpso-blue tabular-nums leading-tight transition-all duration-300" style={{ textShadow: "0 0 8px rgba(0,212,255,0.5)" }}>{filteredStats.planned}</div>
                  <div className="truncate text-xs text-fpso-dim">Future Projects</div>
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
                  className="map-pulse absolute z-10 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border border-fpso-blue bg-fpso-blue outline-none focus:ring-2 focus:ring-fpso-blue/50"
                  style={{
                    left: `${dot.x}%`,
                    top: `${dot.y}%`,
                    animationDelay: dot.delay,
                    "--dot-delay": dot.delay,
                  }}
                  aria-label={`${dot.country} 项目`}
                />
              ))
            )}
          </div>

        </section>

        {/* 图表区域 */}
        <section className="mb-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* 国家分布饼图 */}
          <div className="rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md p-5 shadow-xl hover:shadow-2xl transition-shadow duration-300">
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
          <div className="rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md p-5 shadow-xl hover:shadow-2xl transition-shadow duration-300">
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

          <div className="rounded-lg border border-white/5 bg-fpso-card/40 backdrop-blur-md shadow-xl hover:shadow-2xl transition-shadow duration-300">
            {loading ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">Loading projects…</div>
            ) : filteredProjects.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-fpso-muted">
                No projects found for the selected industry and country.
              </div>
            ) : (
              filteredProjects.map((project) => (
                <motion.div
                  key={project.name}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                  onClick={() => setSelectedProject(project)}
                  className={`project-row group cursor-pointer border-b border-white/5 border-l-4 px-5 py-5 last:border-b-0 transition-all hover:bg-fpso-blue/[0.04] hover:border-white/10 ${statusBorderLClass(project.status)}`}
                >
                  {/* Row 1: status dot + name + country + source */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 items-center gap-2.5">
                      <span
                        className={`mt-0.5 h-2 w-2 flex-shrink-0 rounded-full ${statusDotClass(project.status)}`}
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
                    {/* Status text */}
                    <span className={`text-[11px] font-medium ${statusColorClass(project.status)}`}>
                      {project.status}
                    </span>
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

                  {/* Phase progress bar */}
                  {(() => {
                    const progress = getPhaseProgress(project.status);
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
        const isFpso = (selectedProject.industry ?? "FPSO") === "FPSO";
        const specs = {
          waterDepthM: selectedProject.waterDepthM,
          oilCapacityBpd: selectedProject.oilCapacityBpd,
          gasCapacityMmcmd: selectedProject.gasCapacityMmcmd,
          hullType: selectedProject.hullType,
          fieldName: selectedProject.fieldName,
          operatorName: selectedProject.operatorName,
          basin: selectedProject.basin,
        };
        const rec = parseRecommendation(selectedProject.recommendationJson);
        const showSpecs = hasAnySpecs(specs);
        const showRec = rec !== null;

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

            {/* Tab 导航 —— 仅 FPSO 行业显示 Timeline 标签 */}
            {isFpso && (
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
            )}

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
                  <span className={`h-2 w-2 rounded-full ${statusDotClass(selectedProject.status)}`} style={{ boxShadow: `0 0 6px currentColor` }} />
                  <span className={statusColorClass(selectedProject.status)}>{selectedProject.status || "Unknown"}</span>
                </span>
                {selectedProject.confidence && (
                  <span className={`inline-flex items-center gap-1 rounded-md px-3 py-1 text-sm ${confidenceBadgeClass(selectedProject.confidence)}`}>
                    {selectedProject.confidence}
                  </span>
                )}
              </div>

              {/* follow / unfollow button */}
              {isAuthenticated && (
                <div>
                  <Button
                    variant={isFollowing(selectedProject.name) ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => toggleFollowProject(selectedProject.name)}
                    className={
                      isFollowing(selectedProject.name)
                        ? 'bg-fpso-blue hover:bg-fpso-blue/80 text-white text-xs'
                        : 'border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-xs'
                    }
                  >
                    {isFollowing(selectedProject.name) ? '★ Following' : '☆ Follow'}
                  </Button>
                </div>
              )}

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

              {/* Technical Specs & Material Matching */}
              {(showSpecs || showRec) && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fpso-dim">
                    Technical Specs &amp; Material Matching
                  </h4>
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
                  )}
                  {showRec && (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-fpso-muted">Grades:</span>
                        {rec.grades.map((g) => (
                          <span
                            key={g.grade}
                            className={`rounded px-2 py-0.5 text-xs font-medium ${
                              g.in_factory_scope
                                ? "bg-fpso-blue/10 text-fpso-blue"
                                : "bg-red-500/10 text-red-400 line-through"
                            }`}
                          >
                            {g.grade}
                            {g.in_factory_scope ? "" : " (not producible)"}
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
                  <p className="text-sm text-fpso-muted">No milestone events found for this project.</p>
                  <p className="text-xs text-fpso-dim mt-1">
                    No matching events in candidate_events for this project. Data may appear after the next crawl.
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
              {isFpso && (
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
              )}
            </div>
            )}
          </div>
        </div>
        );
      })()}
    </>
  );
}
