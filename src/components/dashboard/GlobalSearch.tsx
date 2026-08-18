/**
 * GlobalSearch — top-nav project search box (terminal style).
 *
 * Live-searches the full in-memory project list (all 1168+ projects,
 * no maturity filter). Dropdown shows name / country / phase / matched
 * fields in a glass panel. Esc closes, Enter opens the first result.
 */

import { useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import type { Project } from "@/data/projects";
import { searchProjects, SEARCH_FIELD_LABELS } from "@/lib/project_search";
import { phaseLabel, phaseColorClass } from "@/lib/project_phase";

const MAX_RESULTS = 8;

interface GlobalSearchProps {
  projects: Project[];
  value: string;
  onChange: (value: string) => void;
  /** Open the detail modal / panel for the chosen project. */
  onSelect: (project: Project) => void;
}

export default function GlobalSearch({ projects, value, onChange, onSelect }: GlobalSearchProps) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const matches = useMemo(
    () => (value.trim() ? searchProjects(projects, value) : []),
    [projects, value],
  );

  const showDropdown = open && value.trim().length > 0;

  function close() {
    setOpen(false);
    inputRef.current?.blur();
  }

  function choose(project: Project) {
    onSelect(project);
    close();
  }

  return (
    <div className="relative hidden md:block" onKeyDown={(e) => e.stopPropagation()}>
      {/* terminal-style input */}
      <div className="flex items-center">
        <Search className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-fpso-blue/60" />
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              close();
            } else if (e.key === "Enter" && matches.length > 0) {
              e.preventDefault();
              choose(matches[0].project);
            }
          }}
          placeholder="search projects…"
          aria-label="Search projects"
          className="h-8 w-48 rounded-md border border-fpso-border/60 bg-fpso-bg/80 pl-8 pr-7 font-mono text-xs text-fpso-green placeholder:text-fpso-dim outline-none transition-colors focus:border-fpso-blue/50 focus:ring-1 focus:ring-fpso-blue/30 lg:w-64"
        />
        {value && (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            className="absolute right-2 rounded p-0.5 text-fpso-dim hover:text-fpso-fg transition-colors"
            aria-label="Clear search"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* glass results dropdown */}
      {showDropdown && (
        <div className="absolute right-0 top-full z-50 mt-1.5 w-[340px] overflow-hidden rounded-lg border border-white/10 bg-fpso-card/70 shadow-2xl backdrop-blur-xl lg:w-[380px]">
          {matches.length === 0 ? (
            <div className="px-4 py-5 text-center text-xs text-fpso-muted">
              无匹配项目 — 试试项目名 / 国家 / 油田 / 运营商
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto py-1">
              {matches.slice(0, MAX_RESULTS).map(({ project, fields }) => (
                <button
                  key={project.name}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(project)}
                  className="flex w-full flex-col gap-1 px-3.5 py-2 text-left transition-colors hover:bg-fpso-blue/[0.06]"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-mono text-xs font-semibold text-fpso-fg">
                      {project.name}
                    </span>
                    <span className={`flex-shrink-0 text-[10px] font-medium ${phaseColorClass(project.phase)}`}>
                      {phaseLabel(project.phase)}
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[10px] text-fpso-muted">
                    <span className="flex-shrink-0">{project.flag || "🌐"} {project.country}</span>
                    <span className="flex flex-wrap items-center gap-1">
                      {fields.map((f) => (
                        <span
                          key={f}
                          className="inline-flex items-center rounded bg-fpso-blue/10 px-1 py-px font-medium text-fpso-blue/80 ring-1 ring-fpso-blue/15"
                        >
                          {SEARCH_FIELD_LABELS[f] ?? f}
                        </span>
                      ))}
                    </span>
                  </span>
                </button>
              ))}
              {matches.length > MAX_RESULTS && (
                <div className="border-t border-white/5 px-3.5 py-1.5 text-center text-[10px] text-fpso-dim">
                  还有 {matches.length - MAX_RESULTS} 个匹配，继续输入缩小范围
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
