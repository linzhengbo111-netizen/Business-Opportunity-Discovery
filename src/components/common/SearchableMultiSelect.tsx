import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check, X, Search } from "lucide-react";
import type { DropdownOption } from "./ThemeSelect";

/**
 * Searchable multi-select dropdown — same glass style as ThemeSelect.
 * Trigger shows selected items as removable chips; panel has a keyword
 * filter input. Collapsed by default; closes on outside click / Escape.
 */
export function SearchableMultiSelect({
  value,
  onChange,
  options,
  placeholder = "请选择…",
  searchPlaceholder = "搜索…",
  className = "",
}: {
  value: string[];
  onChange: (selected: string[]) => void;
  options: DropdownOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open]);

  const selected = options.filter((o) => value.includes(o.value));
  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(query.trim().toLowerCase()),
  );

  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* Trigger — grows with chips */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex min-h-8 w-full flex-wrap items-center gap-1 rounded-md border bg-fpso-card/70 px-2 py-1 text-left outline-none transition-all backdrop-blur-sm focus-visible:border-fpso-blue/50 focus-visible:ring-2 focus-visible:ring-fpso-blue/50 ${
          open
            ? "border-fpso-blue/50 ring-1 ring-fpso-blue/30 shadow-glow"
            : "border-fpso-border hover:border-fpso-blue/40 hover:bg-fpso-card"
        }`}
      >
        {selected.length === 0 ? (
          <span className="flex-1 truncate text-xs text-fpso-muted/60">
            {placeholder}
          </span>
        ) : (
          selected.map((o) => (
            <span
              key={o.value}
              className="inline-flex items-center gap-1 rounded-full border border-fpso-blue/30 bg-fpso-blue/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-blue"
            >
              {o.label}
              <span
                role="button"
                aria-label={`移除 ${o.label}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onChange(value.filter((x) => x !== o.value));
                }}
                className="cursor-pointer rounded-full p-px text-fpso-blue/70 hover:bg-fpso-blue/20 hover:text-fpso-blue"
              >
                <X className="h-2.5 w-2.5" />
              </span>
            </span>
          ))
        )}
        <ChevronDown
          className={`ml-auto h-3.5 w-3.5 flex-shrink-0 text-fpso-muted transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Panel */}
      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-md border border-fpso-border bg-fpso-card p-1 shadow-lift">
          {/* Keyword filter */}
          <div className="relative m-0.5 mb-1">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-fpso-muted" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              className="h-7 w-full rounded border border-fpso-border bg-fpso-bg/50 pl-7 pr-2 text-xs text-fpso-fg outline-none placeholder:text-fpso-muted/50 focus:border-fpso-blue/50"
            />
          </div>

          {/* Options */}
          <div className="max-h-52 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-fpso-muted">
                无匹配选项
              </p>
            ) : (
              filtered.map((o) => {
                const active = value.includes(o.value);
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => toggle(o.value)}
                    className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                      active
                        ? "bg-fpso-blue/10 font-medium text-fpso-blue"
                        : "text-fpso-fg hover:bg-fpso-bg"
                    }`}
                  >
                    <span className="truncate">{o.label}</span>
                    {active && <Check className="h-3 w-3 flex-shrink-0" />}
                  </button>
                );
              })
            )}
          </div>

          {/* Footer — count + clear */}
          {value.length > 0 && (
            <div className="mt-1 flex items-center justify-between border-t border-fpso-border/60 px-2 py-1.5">
              <span className="text-[10px] text-fpso-muted">
                已选 {value.length} 项
              </span>
              <button
                type="button"
                onClick={() => onChange([])}
                className="cursor-pointer text-[10px] text-fpso-muted transition-colors hover:text-destructive"
              >
                清空
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
