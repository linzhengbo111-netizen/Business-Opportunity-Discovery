import { PanelLeftClose, PanelLeftOpen, RotateCcw, Download, X } from "lucide-react";
import type { Project } from "@/data/projects";
import { Switch } from "@/components/ui/switch";
import { PHASES, PHASE_UNKNOWN, PHASE_HEX } from "@/lib/project_phase";

const INDUSTRY_OPTIONS = [
  "All Industries",
  "FPSO",
  "Desalination",
  "LNG",
  "General Stainless",
] as const;

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
  /** Show all projects including 待挖掘 (default: mature only). */
  showAllProjects: boolean;
  onShowAllProjectsChange: (value: boolean) => void;
}

/** Look up a country's flag emoji from the project list. */
function getCountryFlag(projects: Project[], country: string): string {
  const found = projects.find((p) => p.country.trim() === country.trim() && p.flag);
  return found?.flag ?? "";
}

/** Industry option display label. */
function industryLabel(opt: string): string {
  if (opt === "Desalination") return `${opt} (海水淡化)`;
  if (opt === "General Stainless") return `${opt} (其他不锈钢)`;
  return opt;
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
}: FilterSidebarProps) {
  const hasFilters =
    selectedCountry !== "All Countries" ||
    selectedIndustry !== "All Industries" ||
    selectedConfidence !== "All" ||
    selectedPhases.size > 0;

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
        className={`fixed top-16 left-0 z-40 border-r border-white/5 bg-fpso-card/60 backdrop-blur-md transition-all duration-300 ease-in-out overflow-hidden
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
          className="absolute top-3 right-0 flex h-8 w-8 items-center justify-center rounded-l-md bg-fpso-card/80 text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/50 transition-colors border-y border-l border-white/5"
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
          <div className="px-4 pt-4 pb-2">
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
              <SelectField
                value={selectedCountry}
                onChange={onCountryChange}
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
              </SelectField>
            </FilterGroup>

            {/* Industry filter */}
            <FilterGroup label="Industry">
              <SelectField
                value={selectedIndustry}
                onChange={onIndustryChange}
              >
                {INDUSTRY_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {industryLabel(opt)}
                  </option>
                ))}
              </SelectField>
            </FilterGroup>

            {/* Confidence filter */}
            <FilterGroup label="Confidence">
              <SelectField
                value={selectedConfidence}
                onChange={onConfidenceChange}
              >
                {CONFIDENCE_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </SelectField>
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
                      className="inline-flex items-center rounded-md px-2 py-1 text-[11px] font-medium transition-all border"
                      style={{
                        borderColor: active ? s.color : "rgb(30 40 68 / 0.6)",
                        backgroundColor: active ? `${s.color}18` : "transparent",
                        color: active ? s.color : "#94a3b8",
                      }}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </FilterGroup>

            {/* Export button */}
            {onExport && (
              <div className="pt-3 border-t border-white/5">
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
                      ? "cursor-not-allowed bg-fpso-bg/30 text-fpso-dim border border-white/5"
                      : "bg-fpso-blue/15 text-fpso-blue border border-fpso-blue/30 hover:bg-fpso-blue/25 hover:border-fpso-blue/50 active:scale-[0.98]"
                  }`}
                >
                  <Download className="h-3.5 w-3.5" />
                  导出商机清单
                </button>
                {!exportDisabled && (
                  <p className="mt-1.5 text-[10px] leading-relaxed text-fpso-dim text-center">
                    CSV — 仅含工厂可做的项目
                  </p>
                )}
              </div>
            )}

            {/* Show-all toggle (bottom of sidebar) */}
            <div className="pt-3 border-t border-white/5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium text-fpso-fg leading-snug">
                    显示全部项目（含待挖掘）
                  </p>
                  <p className="mt-0.5 text-[10px] leading-relaxed text-fpso-dim">
                    默认仅展示成熟商机
                  </p>
                </div>
                <Switch
                  checked={showAllProjects}
                  onCheckedChange={onShowAllProjectsChange}
                  aria-label="显示全部项目（含待挖掘）"
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

/** Themed select dropdown. */
function SelectField({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 w-full appearance-none rounded-md border border-white/5 bg-fpso-bg/60 px-2.5 py-1 text-xs text-fpso-fg outline-none transition-colors hover:border-white/10 focus:border-fpso-blue/40 focus:ring-1 focus:ring-fpso-blue/30"
    >
      {children}
    </select>
  );
}
