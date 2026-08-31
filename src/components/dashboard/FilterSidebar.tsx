import { RotateCcw, Download } from "lucide-react";
import type { Project } from "@/data/projects";
import { INDUSTRY_OPTIONS, industryLabel } from "@/data/projects";
import { Switch } from "@/components/ui/switch";
import { ThemeSelect } from "@/components/common/ThemeSelect";
import SidebarShell from "@/components/common/SidebarShell";
import SavedProjectsPanel, { getCountryFlag } from "@/components/common/SavedProjectsPanel";
import { PHASES, PHASE_UNKNOWN } from "@/lib/project_phase";

const CONFIDENCE_OPTIONS = ["High & Medium", "High", "Medium", "Low", "All"] as const;

export const ALL_PHASES = "All Phases";

/** 阶段下拉选项 — 与收藏项目面板的 All Phases 筛选一致。 */
const PHASE_FILTER_OPTIONS = [
  { value: ALL_PHASES, label: ALL_PHASES },
  ...PHASES.map((label) => ({ value: label, label })),
  { value: PHASE_UNKNOWN, label: PHASE_UNKNOWN },
];

interface FilterSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  countries: string[];
  projects: Project[];
  selectedCountry: string;
  selectedIndustry: string;
  selectedConfidence: string;
  selectedPhase: string;
  onCountryChange: (value: string) => void;
  onIndustryChange: (value: string) => void;
  onConfidenceChange: (value: string) => void;
  onPhaseChange: (phase: string) => void;
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

export default function FilterSidebar({
  collapsed,
  onToggle,
  countries,
  projects,
  selectedCountry,
  selectedIndustry,
  selectedConfidence,
  selectedPhase,
  onCountryChange,
  onIndustryChange,
  onConfidenceChange,
  onPhaseChange,
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
    selectedPhase !== ALL_PHASES;

  const exportDisabled = !onExport || filteredCount === 0;

  return (
    <SidebarShell
      collapsed={collapsed}
      onToggle={onToggle}
      collapsedLabel="Filters"
      collapsedIndicator={hasFilters}
      collapsedIndicatorTitle="Filters active"
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

        {/* Phase filter — All Phases 单选下拉，与 Region/Industry 同格式 */}
        <FilterGroup label="Phase">
          <ThemeSelect
            value={selectedPhase}
            onChange={onPhaseChange}
            options={PHASE_FILTER_OPTIONS}
          />
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
    </SidebarShell>
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

