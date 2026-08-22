/**
 * Battle Cards Page — 战报中心
 * 只展示 grade A/B 的项目（评分实时计算），按评分降序。
 * 卡片网格展示作战卡摘要，点击弹出完整作战卡，支持导出 CSV。
 *
 * Fetch 逻辑与 Dashboard 保持一致：projects 表 + sampleProjects 兜底，断网不白屏。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName, sortPriorityFirst, priorityProjectRankByName } from "@/data/project_aliases";
import { supabase } from "@/db/supabase";
import { phaseFromRow } from "@/lib/project_phase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { useTimelineEventCounts } from "@/hooks/useTimelineEventCounts";
import { filterMatureProjects } from "@/lib/project_maturity";
import { parseCorrosiveMedia } from "@/lib/material_matcher";
import { scoreOpportunity, scoreBadgeClass } from "@/lib/opportunity_scorer";
import { generateBattleCard, type BattleCard } from "@/lib/battle_card";
import { exportOpportunityList } from "@/lib/export_opportunities";
import { usePushAnalysisState } from "@/hooks/usePushAnalysis";
import { PushSourceBadge } from "@/components/dashboard/PushAnalysisPanel";
import BattleCardWrapper from "@/components/dashboard/BattleCard";
import { useRequireLogin } from "@/hooks/useRequireLogin";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Download, MapPin, Package, Layers, CalendarDays, User, ArrowRight } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  shared helpers (same semantics as DashboardPage)                   */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  page                                                               */
/* ------------------------------------------------------------------ */

interface ScoredCard {
  project: Project;
  card: BattleCard;
  score: number;
  grade: "A" | "B" | "C" | "D";
}

/** One summary card in the grid — own component so the AI analysis only
 *  fires when the card scrolls into view (one LLM call per project). */
function BattleSummaryCard({
  project,
  card,
  score,
  grade,
  onOpen,
}: {
  project: Project;
  card: BattleCard;
  score: number;
  grade: "A" | "B" | "C" | "D";
  onOpen: (p: Project) => void;
}) {
  const cardRef = useRef<HTMLButtonElement | null>(null);
  const [inView, setInView] = useState(false);

  // AI 分析仅在卡片进入视口后触发 — 规则引擎结果先行显示，AI 返回后替换
  useEffect(() => {
    const el = cardRef.current;
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

  const products =
    analysis && analysis.recommended_products.length > 0
      ? analysis.recommended_products.map((p) => p.product).join("、")
      : card.whatToPush.join("、");
  const materials =
    analysis && analysis.recommended_materials.length > 0
      ? analysis.recommended_materials.map((m) => m.grade).join("、")
      : card.materialGrades.join("、");
  const windowText =
    analysis?.procurement_window.range && analysis.procurement_window.range !== "待补充"
      ? analysis.procurement_window.range
      : card.whenToContact;

  /** Amber "AI 分析中…" placeholder shown while the LLM call is in flight. */
  const analyzing = (
    <span className="inline-flex items-center rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400 animate-pulse">
      AI 分析中…
    </span>
  );

  return (
    <button
      ref={cardRef}
      type="button"
      onClick={() => onOpen(project)}
      className="group rounded-xl border border-white/5 bg-fpso-card/60 p-5 text-left backdrop-blur-md transition-all hover:border-fpso-blue/30 hover:shadow-lg hover:shadow-fpso-blue/5"
    >
      {/* name + grade */}
      <div className="mb-3 flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold leading-snug text-fpso-fg group-hover:text-fpso-blue">
          {card.projectName}
        </h2>
        <span className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ${scoreBadgeClass(grade)}`}>
          {grade} · {score}
        </span>
      </div>

      <p className="mb-4 flex items-center gap-1.5 text-xs text-fpso-muted">
        <MapPin className="h-3.5 w-3.5" />
        {card.country}
      </p>

      {/* summary rows — AI 结果优先，规则引擎兜底；LLM 请求中显示加载态 */}
      <div className="space-y-2 text-sm">
        <p className="flex items-start gap-2 text-fpso-fg/80">
          <Package className="mt-0.5 h-4 w-4 flex-shrink-0 text-fpso-blue/70" />
          <span><span className="text-fpso-muted">推荐产品:</span> {loading ? "AI 分析中…" : products}</span>
        </p>
        <p className="flex items-start gap-2 text-fpso-fg/80">
          <Layers className="mt-0.5 h-4 w-4 flex-shrink-0 text-fpso-blue/70" />
          <span><span className="text-fpso-muted">推荐材质:</span> {loading ? "AI 分析中…" : materials}</span>
        </p>
        <p className="flex items-start gap-2 text-fpso-fg/80">
          <CalendarDays className="mt-0.5 h-4 w-4 flex-shrink-0 text-fpso-blue/70" />
          <span className="flex flex-wrap items-center gap-1.5">
            <span><span className="text-fpso-muted">采购时间窗:</span> {loading ? "AI 分析中…" : windowText}</span>
            {loading ? analyzing : analysis && <PushSourceBadge source={analysis.source} />}
          </span>
        </p>
        <p className="flex items-start gap-2 text-fpso-fg/80">
          <User className="mt-0.5 h-4 w-4 flex-shrink-0 text-fpso-blue/70" />
          <span><span className="text-fpso-muted">联系谁:</span> {card.whoToContact.recommendedRole}</span>
        </p>
        <p className="flex items-start gap-2 text-fpso-fg/80">
          <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-fpso-blue/70" />
          <span><span className="text-fpso-muted">下一步:</span> {card.nextAction}</span>
        </p>
      </div>
    </button>
  );
}

export default function BattleCardsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const { version, status: connectionStatus } = useProjectRealtime();
  const timelineEventCounts = useTimelineEventCounts(version);
  const requireLogin = useRequireLogin();

  // ---- 从 Supabase 获取项目数据（projects 表，空则兜底 sampleProjects）----
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      const { data, error } = await supabase.from("projects").select("*");

      if (cancelled) return;

      if (error) {
        console.error(`[BattleCards] projects fetch FAILED: ${error.message}`);
        setProjects(sampleProjects);
      } else {
        const mapped = (data ?? []).map(mapRowToProject);
        if (mapped.length > 0) {
          console.log(`[BattleCards] projects fetch OK: ${mapped.length} rows`);
          setProjects(mapped);
        } else {
          console.warn("[BattleCards] projects EMPTY. Falling back to sampleProjects.");
          setProjects(sampleProjects);
        }
      }
    }

    loadData().finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [version]);

  // ---- 实时评分 + A/B 过滤 + 按分降序 + 生成作战卡摘要 ----
  // 战报中心只展示成熟商机（技术参数 + 时间线事件齐备），
  // 潜在项目生成不了有价值的战报。
  const abCards = useMemo<ScoredCard[]>(() => {
    const scored = filterMatureProjects(projects, timelineEventCounts, false)
      .map((project) => {
        const scoreResult = scoreOpportunity(project);
        return {
          project,
          card: generateBattleCard(project),
          score: scoreResult.totalScore,
          grade: scoreResult.grade,
        };
      })
      .filter((item) => item.grade === "A" || item.grade === "B")
      .sort((a, b) => b.score - a.score);
    // 置顶项目按 PRIORITY_PROJECT_NAMES 顺序排最前，其余保持评分降序。
    return sortPriorityFirst(scored, (item) => priorityProjectRankByName(item.project.name));
  }, [projects, timelineEventCounts]);

  const handleExport = () => {
    if (!requireLogin()) return;
    exportOpportunityList(
      abCards.map((item) => item.project),
      window.location.origin,
    );
  };

  return (
    <div className="min-h-screen bg-fpso-bg text-fpso-fg">
      <PageMeta title="战报中心 — FPSO Projects" description="A/B 级商机作战卡" />
      <Header />

      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* page header */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
              战报中心
            </h1>
            <p className="mt-1 text-sm text-fpso-muted">
              A / B 级商机作战卡 · 仅成熟商机 · 置顶项目优先 · 其余按评分降序 · {abCards.length} 个项目
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium">
              <span className={`h-1.5 w-1.5 rounded-full ${connectionStatus === "connected" ? "bg-emerald-400" : "bg-amber-400"}`} />
              {connectionStatus === "connected" ? "LIVE" : "STALE"}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={abCards.length === 0}
              className="border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10"
            >
              <Download className="mr-1.5 h-4 w-4" />
              导出全部 CSV
            </Button>
          </div>
        </div>

        {/* loading / empty states */}
        {loading ? (
          <p className="py-16 text-center text-fpso-muted">加载中…</p>
        ) : abCards.length === 0 ? (
          <p className="py-16 text-center text-fpso-muted">暂无 A / B 级商机项目</p>
        ) : (
          /* card grid */
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {abCards.map(({ project, card, score, grade }) => (
              <BattleSummaryCard
                key={project.name}
                project={project}
                card={card}
                score={score}
                grade={grade}
                onOpen={setSelectedProject}
              />
            ))}
          </div>
        )}
      </main>

      {/* full battle card dialog */}
      <Dialog open={selectedProject !== null} onOpenChange={(open) => !open && setSelectedProject(null)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-auto">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold text-fpso-fg">
              完整作战卡
            </DialogTitle>
          </DialogHeader>
          {selectedProject && (
            <BattleCardWrapper project={selectedProject} baseUrl={window.location.origin} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
