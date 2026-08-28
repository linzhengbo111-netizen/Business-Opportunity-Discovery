import { useState } from "react";
import { PanelLeftClose, PanelLeftOpen, RotateCcw, Download, X, ChevronDown, Star } from "lucide-react";
import type { Project } from "@/data/projects";
import { INDUSTRY_OPTIONS, industryLabel, countryToFlagEmoji, ALL_INDUSTRIES } from "@/data/projects";
import { Switch } from "@/components/ui/switch";
import { ThemeSelect } from "@/components/common/ThemeSelect";
import { PHASES, PHASE_UNKNOWN, PHASE_HEX, phaseLabel } from "@/lib/project_phase";

const CONFIDENCE_OPTIONS = ["High & Medium", "High", "Medium", "Low", "All"] as const;

/** 10 phase filter chips — 9 lifecycle phases + Unknown. */
const PHASE_CHIP_OPTIONS = [
  ...PHASES.map((label) => ({ label, color: PHASE_HEX[label] })),
  { label: PHASE_UNKNOWN, color: PHASE_HEX[PHASE_UNKNOWN] },
] as const;

const SIDEBAR_EXPANDED = 260;
const SIDEBAR_COLLAPSED = 48;
const NAV_HEIGHT = 64; // h-16

interface FilterSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  countries: string[];
  projects: Project[];
  selectedCountry: string;
  selectedIndustry: string;
  selectedConfidence: string;
  selectedPhases: Set<string>;
  onCountryChange: (value: string) => void;
  onIndustryChange: (value: string) => void;
  onConfidenceChange: (value: string) => void;
  onPhaseToggle: (phase: string) => void;
  onClear: () => void;
  /** Called when user clicks the export button. */
  onExport?: () => void;
  /** Number of projects in the current filtered view. */
  filteredCount?: number;
  /** Show all projects including 待挖掘 (true = mature filter off, the default). */
  showAllProjects: boolean;
  onShowAllProjectsChange: (value: boolean) => void;
  /** 收藏的项目（当前 projects 数据中解析出的实时列表）。 */
  savedProjects?: Project[];
  /** 点击收藏条目时回调 — 由页面打开项目详情。 */
  onOpenProject?: (project: Project) => void;
}

/** Look up a country's flag emoji — ISO code map first, project rows as fallback. */
function getCountryFlag(projects: Project[], country: string): string {
  return (
    countryToFlagEmoji(country) ||
    projects.find((p) => p.country.trim() === country.trim() && p.flag)?.flag ||
    ""
  );
}

export default function FilterSidebar({
  collapsed,
  onToggle,
  countries,
  projects,
  selectedCountry,
  selectedIndustry,
  selectedConfidence,
  selectedPhases,
  onCountryChange,
  onIndustryChange,
  onConfidenceChange,
  onPhaseToggle,
  onClear,
  onExport,
  filteredCount = 0,
  showAllProjects,
  onShowAllProjectsChange,
  savedProjects = [],
  onOpenProject,
}: FilterSidebarProps) {
  const hasFilters =
    selectedCountry !== "All Countries" ||
    selectedIndustry !== "All Industries" ||
    selectedConfidence !== "All" ||
    (selectedPhases.size > 0 && selectedPhases.size < PHASE_CHIP_OPTIONS.length);

  const exportDisabled = !onExport || filteredCount === 0;

  return (
    <>
      {/* Mobile backdrop overlay */}
      <div
        className={`md:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${
          collapsed ? "opacity-0 pointer-events-none" : "opacity-100"
        }`}
        onClick={onToggle}
        aria-hidden="true"
      />

      {/* Sidebar — fixed on desktop, overlay on mobile */}
      <aside
        className={`fixed top-16 left-0 z-40 border-r border-fpso-border bg-fpso-card/70 backdrop-blur-md transition-all duration-300 ease-in-out overflow-hidden
          max-md:shadow-2xl
          ${collapsed ? "max-md:-translate-x-full" : "max-md:translate-x-0"}
        `}
        style={{
          width: collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED,
          height: `calc(100vh - ${NAV_HEIGHT}px)`,
        }}
      >
        {/* Collapse toggle — always visible */}
        <button
          onClick={onToggle}
          className="absolute top-3 right-0 flex h-8 w-8 items-center justify-center rounded-l-md bg-fpso-card/80 text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/50 transition-colors border-y border-l border-border"
          title={collapsed ? "Expand filters" : "Collapse filters"}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>

        {/* Mobile close button */}
        <button
          onClick={onToggle}
          className="md:hidden absolute top-3 right-10 flex h-8 w-8 items-center justify-center rounded-md text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/30 transition-colors"
          title="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Collapsed state: icon column */}
        {collapsed && (
          <div className="flex flex-col items-center gap-4 pt-16">
            <span className="text-fpso-muted text-[10px] font-semibold uppercase tracking-widest writing-vertical">
              Filters
            </span>
            {hasFilters && (
              <span className="inline-flex h-2 w-2 rounded-full bg-fpso-blue" title="Filters active" />
            )}
          </div>
        )}

        {/* Expanded content */}
        <div
          className="transition-opacity duration-200 overflow-y-auto h-full"
          style={{ opacity: collapsed ? 0 : 1, pointerEvents: collapsed ? "none" : "auto" }}
        >
          {/* 收藏项目面板 — 顶部，独立于主筛选状态 */}
          <div className="px-4 pt-4">
            <SavedProjectsPanel
              countries={countries}
              savedProjects={savedProjects}
              onOpenProject={onOpenProject}
            />
          </div>
          <div className="mx-4 mt-3 border-t border-fpso-border" />

          <div className="px-4 pt-3 pb-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-fpso-dim">
                Filters
              </span>
              {hasFilters && (
                <button
                  onClick={onClear}
                  className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/30 transition-colors"
                  title="Clear all filters"
                >
                  <RotateCcw className="h-3 w-3" />
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="space-y-5 px-4 pb-6">
            {/* Region filter */}
            <FilterGroup label="Region">
              <ThemeSelect
                value={selectedCountry}
                onChange={onCountryChange}
                options={[
                  { value: "All Countries", label: "All Countries" },
                  ...countries.map((c) => ({
                    value: c,
                    label: getCountryFlag(projects, c) ? `${getCountryFlag(projects, c)} ${c}` : c,
                  })),
                ]}
              />
            </FilterGroup>

            {/* Industry filter */}
            <FilterGroup label="Industry">
              <ThemeSelect
                value={selectedIndustry}
                onChange={onIndustryChange}
                options={INDUSTRY_OPTIONS.map((opt) => ({
                  value: opt,
                  label: industryLabel(opt),
                }))}
              />
            </FilterGroup>

            {/* Confidence filter */}
            <FilterGroup label="Confidence">
              <ThemeSelect
                value={selectedConfidence}
                onChange={onConfidenceChange}
                options={CONFIDENCE_OPTIONS.map((opt) => ({
                  value: opt,
                  label: opt,
                }))}
              />
            </FilterGroup>

            {/* Phase multi-select — 10 chips */}
            <FilterGroup label="Phase">
              <div className="flex flex-wrap gap-1.5">
                {PHASE_CHIP_OPTIONS.map((s) => {
                  const active = selectedPhases.has(s.label);
                  return (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => onPhaseToggle(s.label)}
                      className={`inline-flex items-center rounded-md px-2 py-1 text-[11px] font-medium transition-all border ${
                        active
                          ? ""
                          : "border-fpso-border bg-fpso-card/60 text-fpso-muted hover:border-fpso-blue/40 hover:text-fpso-fg hover:bg-white"
                      }`}
                      style={
                        active
                          ? { borderColor: s.color, backgroundColor: `${s.color}18`, color: s.color }
                          : undefined
                      }
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </FilterGroup>

            {/* Export button */}
            {onExport && (
              <div className="pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={onExport}
                  disabled={exportDisabled}
                  title={
                    exportDisabled
                      ? "Export disabled: no projects in current view"
                      : `Export ${filteredCount} visible projects to CSV (only factory-qualified items included)`
                  }
                  className={`inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-semibold transition-all ${
                    exportDisabled
                      ? "cursor-not-allowed bg-fpso-bg/30 text-fpso-dim border border-border"
                      : "bg-fpso-blue/15 text-fpso-blue border border-fpso-blue/30 hover:bg-fpso-blue/25 hover:border-fpso-blue/50 active:scale-[0.98]"
                  }`}
                >
                  <Download className="h-3.5 w-3.5" />
                  导出商机清单
                </button>
              </div>
            )}

            {/* Mature-only toggle (bottom of sidebar) — off by default, all projects shown */}
            <div className="pt-3 border-t border-border">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium text-fpso-fg leading-snug">
                    仅显示成熟商机
                  </p>
                  <p className="mt-0.5 text-[10px] leading-relaxed text-fpso-dim">
                    关闭显示全部项目（含待挖掘）
                  </p>
                </div>
                <Switch
                  checked={!showAllProjects}
                  onCheckedChange={(matureOnly) => onShowAllProjectsChange(!matureOnly)}
                  aria-label="仅显示成熟商机"
                />
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

/** Small labeled filter group wrapper. */
function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
        {label}
      </label>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  收藏项目面板 — 顶部区域（独立筛选状态）                              */
/* ------------------------------------------------------------------ */

const ALL_PHASES = "All Phases";

const PHASE_FILTER_OPTIONS = [
  { value: ALL_PHASES, label: ALL_PHASES },
  ...PHASES.map((label) => ({ value: label, label })),
  { value: PHASE_UNKNOWN, label: PHASE_UNKNOWN },
];

/** 侧边栏顶部收藏面板：标题+数量、折叠开关、迷你筛选器、收藏列表。 */
function SavedProjectsPanel({
  countries,
  savedProjects,
  onOpenProject,
}: {
  countries: string[];
  savedProjects: Project[];
  onOpenProject?: (project: Project) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [fCountry, setFCountry] = useState("All Countries");
  const [fIndustry, setFIndustry] = useState(ALL_INDUSTRIES);
  const [fPhase, setFPhase] = useState(ALL_PHASES);

  const filtered = savedProjects.filter((p) => {
    if (fCountry !== "All Countries" && p.country.trim() !== fCountry) return false;
    if (fIndustry !== ALL_INDUSTRIES && (p.industry ?? "FPSO") !== fIndustry) return false;
    if (fPhase !== ALL_PHASES && phaseLabel(p.phase) !== fPhase) return false;
    return true;
  });

  return (
    <div className="rounded-lg border border-fpso-border bg-fpso-bg/50 p-3">
      {/* 标题行 — 折叠开关 + 数量 */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={expanded}
        title={expanded ? "收起收藏项目" : "展开收藏项目"}
      >
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-fpso-dim">
          <Star
            className={`h-3.5 w-3.5 text-fpso-gold ${
              savedProjects.length > 0 ? "fill-fpso-gold" : ""
            }`}
          />
          收藏项目
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="rounded bg-fpso-gold/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold tabular-nums text-fpso-gold">
            {savedProjects.length}
          </span>
          <ChevronDown
            className={`h-3.5 w-3.5 text-fpso-muted transition-transform duration-200 ${
              expanded ? "" : "-rotate-90"
            }`}
          />
        </span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {/* 迷你筛选器 — 独立状态，不影响主内容区筛选 */}
          <div className="grid grid-cols-1 gap-1.5">
            <ThemeSelect
              value={fCountry}
              onChange={setFCountry}
              options={[
                { value: "All Countries", label: "All Countries" },
                ...countries.map((c) => ({
                  value: c,
                  label: getCountryFlag(savedProjects, c) ? `${getCountryFlag(savedProjects, c)} ${c}` : c,
                })),
              ]}
            />
            <ThemeSelect
              value={fIndustry}
              onChange={setFIndustry}
              options={INDUSTRY_OPTIONS.map((opt) => ({
                value: opt,
                label: industryLabel(opt),
              }))}
            />
            <ThemeSelect value={fPhase} onChange={setFPhase} options={PHASE_FILTER_OPTIONS} />
          </div>

          {/* 收藏列表 */}
          {savedProjects.length === 0 ? (
            <p className="rounded-md border border-dashed border-fpso-border px-2 py-3 text-center text-[11px] text-fpso-dim">
              暂无收藏项目
            </p>
          ) : filtered.length === 0 ? (
            <p className="rounded-md border border-dashed border-fpso-border px-2 py-3 text-center text-[11px] text-fpso-dim">
              无匹配项目
            </p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-y-auto pr-0.5">
              {filtered.map((p) => {
                const label = phaseLabel(p.phase);
                const color = PHASE_HEX[label];
                return (
                  <li key={`${p.name}-${p.country}`}>
                    <button
                      type="button"
                      onClick={() => onOpenProject?.(p)}
                      className="group flex w-full items-center gap-2 rounded-md border border-transparent bg-fpso-card/70 px-2.5 py-2 text-left transition-colors hover:border-fpso-gold/40 hover:bg-white"
                      title={`${p.name} — ${p.country}`}
                    >
                      <span className="text-xs leading-none">{p.flag || "•"}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-fpso-fg transition-colors group-hover:text-fpso-blue">
                          {p.name}
                        </span>
                        <span className="block truncate text-[10px] text-fpso-dim">
                          {p.country}
                        </span>
                      </span>
                      <span
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium"
                        style={{ color, backgroundColor: `${color}18` }}
                      >
                        {label}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
