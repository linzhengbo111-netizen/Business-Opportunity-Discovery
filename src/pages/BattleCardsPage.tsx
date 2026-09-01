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
import PageHeader from "@/components/common/PageHeader";
import SidebarShell, { SIDEBAR_EXPANDED, SIDEBAR_COLLAPSED } from "@/components/common/SidebarShell";
import SavedProjectsPanel from "@/components/common/SavedProjectsPanel";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES, normalizeIndustry } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { fetchAllRows } from "@/db/supabase";
import { phaseFromRow, PHASE_UNKNOWN } from "@/lib/project_phase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { useTimelineEventCounts } from "@/hooks/useTimelineEventCounts";
import { hasTimelineData } from "@/lib/project_maturity";
import { parseCorrosiveMedia } from "@/lib/material_matcher";
import { scoreOpportunity, scoreBadgeClass } from "@/lib/opportunity_scorer";
import { generateBattleCard, type BattleCard } from "@/lib/battle_card";
import { exportOpportunityList } from "@/lib/export_opportunities";
import { usePushAnalysisState } from "@/hooks/usePushAnalysis";
import { useSavedProjects } from "@/hooks/useSavedProjects";
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
    <span className="inline-flex items-center rounded bg-fpso-orange/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-orange animate-pulse">
      AI 分析中…
    </span>
  );

  return (
    <button
      ref={cardRef}
      type="button"
      onClick={() => onOpen(project)}
      className="group rounded-xl border border-fpso-border bg-fpso-card/70 p-5 text-left backdrop-blur-md transition-all hover:border-fpso-blue/40 hover:shadow-glow"
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const { version } = useProjectRealtime();
  const timelineEventCounts = useTimelineEventCounts(version);
  const requireLogin = useRequireLogin();
  const { savedProjects } = useSavedProjects(projects);

  // 收藏面板迷你筛选器用国家列表
  const countries = useMemo(
    () => [...new Set(projects.map((p) => p.country.trim()).filter(Boolean))].sort(),
    [projects],
  );

  // ---- 从 Supabase 获取项目数据（projects 表，空则兜底 sampleProjects）----
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      // 分页拉取全量 — 单次 select 上限 1000 行，DB 现有 1212+ 行。
      const { data, error } = await fetchAllRows("projects", "*", { orderBy: "name" });

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

  // ---- 实时评分 + 高质量过滤 + 按分降序 + 生成作战卡摘要 ----
  // 战报中心展示条件（相对放宽，避免只剩 1 张卡）：
  //   1. 有 accepted 时间线事件 + 阶段明确（不再要求技术参数齐备）。
  //   2. 排除 Commissioning（调试期无新建采购机会）。Delivery 不再排除，
  //      按正常规则参与评分排序。
  //   3. 评分 >= 55（A/B 全部 + 高分 C）。UK 噪音项目得分低，自然被挡。
  const abCards = useMemo<ScoredCard[]>(() => {
    return projects
      .filter((project) => {
        const hasPhase = project.phase != null && project.phase !== PHASE_UNKNOWN;
        return hasPhase && hasTimelineData(project, timelineEventCounts);
      })
      .map((project) => {
        const scoreResult = scoreOpportunity(project);
        return {
          project,
          card: generateBattleCard(project),
          score: scoreResult.totalScore,
          grade: scoreResult.grade,
        };
      })
      .filter((item) => {
        const phase = item.project.phase;
        if (phase === "Commissioning") return false;
        return item.score >= 55;
      })
      .sort((a, b) => b.score - a.score);
  }, [projects, timelineEventCounts]);

  const handleExport = () => {
    if (!requireLogin()) return;
    void exportOpportunityList(
      abCards.map((item) => item.project),
      window.location.origin,
    );
  };

  return (
    <div className="min-h-screen text-fpso-fg">
      <PageMeta title="战报中心" description="高质量商机作战卡" />
      <Header onProjectSelect={setSelectedProject} />

      <div className="max-w-7xl mx-auto">
        {/* 左侧栏 — 收藏项目面板，外壳与商机看板一致 */}
        <SidebarShell
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          collapsedLabel="Saved"
        >
          <div className="px-4 pt-4">
            <SavedProjectsPanel
              countries={countries}
              savedProjects={savedProjects}
              onOpenProject={(project) => setSelectedProject(project)}
            />
          </div>
        </SidebarShell>

      <main
        className="flex-1 min-w-0 px-4 py-8 md:px-6 transition-all duration-300 ease-in-out max-md:!ml-0"
        style={{ marginLeft: sidebarCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED }}
      >
        {/* page header — 统一 PageHeader */}
        <PageHeader
          title={<span className="neon-glow">战报中心</span>}
          subtitle={`高质量商机作战卡 · ${abCards.length} 个项目`}
          actions={
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
          }
        />

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
      </div>

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
