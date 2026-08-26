import { PanelLeftClose, PanelLeftOpen, RotateCcw, Download, X } from "lucide-react";
import type { Project } from "@/data/projects";
import { INDUSTRY_OPTIONS, industryLabel, countryToFlagEmoji } from "@/data/projects";
import { Switch } from "@/components/ui/switch";
import { ThemeSelect } from "@/components/common/ThemeSelect";
import { PHASES, PHASE_UNKNOWN, PHASE_HEX } from "@/lib/project_phase";

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
