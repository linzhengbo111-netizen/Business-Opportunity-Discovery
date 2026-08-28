/**
 * SavedProjectsPanel — 侧边栏顶部收藏项目面板
 * 商机看板 / 战报中心共用：标题+数量、折叠开关、迷你筛选器、收藏列表。
 * 迷你筛选器状态独立，不影响页面主筛选。
 */

import { useState } from "react";
import { Star, ChevronDown } from "lucide-react";
import type { Project } from "@/data/projects";
import { INDUSTRY_OPTIONS, industryLabel, countryToFlagEmoji, ALL_INDUSTRIES } from "@/data/projects";
import { ThemeSelect } from "@/components/common/ThemeSelect";
import { PHASES, PHASE_UNKNOWN, PHASE_HEX, phaseLabel } from "@/lib/project_phase";

/** Look up a country's flag emoji — ISO code map first, project rows as fallback. */
export function getCountryFlag(projects: Project[], country: string): string {
  return (
    countryToFlagEmoji(country) ||
    projects.find((p) => p.country.trim() === country.trim() && p.flag)?.flag ||
    ""
  );
}

const ALL_PHASES = "All Phases";

const PHASE_FILTER_OPTIONS = [
  { value: ALL_PHASES, label: ALL_PHASES },
  ...PHASES.map((label) => ({ value: label, label })),
  { value: PHASE_UNKNOWN, label: PHASE_UNKNOWN },
];

export default function SavedProjectsPanel({
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
