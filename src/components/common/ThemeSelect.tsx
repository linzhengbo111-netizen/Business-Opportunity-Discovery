import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check } from "lucide-react";

/** Themed custom dropdown option. */
export interface DropdownOption {
  value: string;
  label: string;
}

/**
 * Themed custom dropdown — glass trigger + floating panel with check mark.
 * Replaces native <select> so the popup matches the site design system.
 */
export function ThemeSelect({
  value,
  onChange,
  options,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  options: DropdownOption[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  const current = options.find((o) => o.value === value);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex h-8 w-full items-center justify-between gap-2 rounded-md border bg-fpso-card/70 px-2.5 py-1 text-xs text-fpso-fg outline-none transition-all backdrop-blur-sm ${
          open
            ? "border-fpso-blue/50 ring-1 ring-fpso-blue/30 shadow-glow"
            : "border-fpso-border hover:border-fpso-blue/40 hover:bg-fpso-card"
        }`}
      >
        <span className="truncate">{current?.label ?? value}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 flex-shrink-0 text-fpso-muted transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 max-h-60 overflow-y-auto rounded-md border border-fpso-border bg-fpso-card p-1 shadow-lift">
          {options.map((o) => {
            const active = o.value === value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
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
          })}
        </div>
      )}
    </div>
  );
}
