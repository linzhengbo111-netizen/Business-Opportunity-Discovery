/**
 * Project Phase System — replaces the legacy 4-value status taxonomy
 * (Under Construction / Planned / Delivered / Unknown) with 9 standardized
 * lifecycle phases + Unknown.
 *
 * Lifecycle order (Concept → Delivery). When several phases match a project,
 * the latest phase in this order wins.
 *
 * Color semantics (sales opportunity view):
 *   早期 Concept/Planning/Design        → gray   (机会遥远)
 *   中期 Approval/EPC Award/Procurement → orange / yellow (Procurement = 核心商机窗口)
 *   后期 Construction/Commissioning/Delivery → blue / green
 *
 * Single source of truth for phase names, colors, groups, progress, and
 * legacy-data compatibility. Frontend pages and scorers import from here.
 */

export const PHASES = [
  "Concept",
  "Planning",
  "Design",
  "Approval",
  "EPC Award",
  "Procurement",
  "Construction",
  "Commissioning",
  "Delivery",
] as const;

export type ProjectPhase = (typeof PHASES)[number];

export const PHASE_SET: ReadonlySet<string> = new Set<string>(PHASES);

/** Display value used for projects whose phase is unknown / not yet judged. */
export const PHASE_UNKNOWN = "Unknown";

/** All filterable phase labels, including Unknown (10 options). */
export const PHASE_OPTIONS: readonly string[] = [...PHASES, PHASE_UNKNOWN];

/** Lifecycle index — later phases win when multiple signals match. */
export const PHASE_ORDER: Record<string, number> = Object.fromEntries(
  PHASES.map((p, i) => [p, i]),
);

/* ------------------------------------------------------------------ */
/* Phase groups (stat cards + grouping semantics)                      */
/* ------------------------------------------------------------------ */

export type PhaseGroup = "early" | "mid" | "late" | "unknown";

export function phaseGroup(phase: string | null | undefined): PhaseGroup {
  if (!phase) return "unknown";
  const idx = PHASE_ORDER[phase];
  if (idx == null) return "unknown";
  if (idx <= 2) return "early";   // Concept / Planning / Design
  if (idx <= 5) return "mid";     // Approval / EPC Award / Procurement
  return "late";                  // Construction / Commissioning / Delivery
}

export const PHASE_GROUP_LABELS: Record<PhaseGroup, string> = {
  early: "Early",
  mid: "Mid",
  late: "Late",
  unknown: "Unknown",
};

/* ------------------------------------------------------------------ */
/* Colors                                                              */
/* ------------------------------------------------------------------ */

/** Hex colors for charts (mirror the tailwind classes below). */
export const PHASE_HEX: Record<string, string> = {
  Concept: "#64748b",
  Planning: "#64748b",
  Design: "#94a3b8",
  Approval: "#ff9f43",
  "EPC Award": "#ff9f43",
  Procurement: "#facc15", // yellow — core business window
  Construction: "#00d4ff",
  Commissioning: "#10b981",
  Delivery: "#10b981",
  [PHASE_UNKNOWN]: "#64748b",
};

/** Text color class for inline phase labels. */
export function phaseColorClass(phase: string | null | undefined): string {
  switch (phase) {
    case "Concept":
    case "Planning":
    case "Design":
      return "text-fpso-muted";
    case "Approval":
    case "EPC Award":
      return "text-fpso-orange";
    case "Procurement":
      return "text-yellow-400";
    case "Construction":
      return "text-fpso-blue";
    case "Commissioning":
    case "Delivery":
      return "text-fpso-green";
    default:
      return "text-fpso-muted";
  }
}

/** Dot / indicator class for phase markers. */
export function phaseDotClass(phase: string | null | undefined): string {
  switch (phase) {
    case "Concept":
    case "Planning":
    case "Design":
      return "bg-fpso-muted";
    case "Approval":
    case "EPC Award":
      return "bg-fpso-orange";
    case "Procurement":
      return "bg-yellow-400";
    case "Construction":
      return "bg-fpso-blue";
    case "Commissioning":
    case "Delivery":
      return "bg-fpso-green";
    default:
      return "bg-fpso-muted";
  }
}

/** Badge (pill) class for phase chips in tables/cards. */
export function phaseBgClass(phase: string | null | undefined): string {
  switch (phase) {
    case "Concept":
    case "Planning":
    case "Design":
      return "bg-fpso-muted/15 text-fpso-muted";
    case "Approval":
    case "EPC Award":
      return "bg-fpso-orange/15 text-fpso-orange";
    case "Procurement":
      return "bg-yellow-400/15 text-yellow-400";
    case "Construction":
      return "bg-fpso-blue/15 text-fpso-blue";
    case "Commissioning":
    case "Delivery":
      return "bg-fpso-green/15 text-fpso-green";
    default:
      return "bg-fpso-muted/15 text-fpso-muted";
  }
}

/** Left border color class for project rows. */
export function phaseBorderLClass(phase: string | null | undefined): string {
  switch (phase) {
    case "Concept":
    case "Planning":
    case "Design":
      return "border-l-fpso-muted";
    case "Approval":
    case "EPC Award":
      return "border-l-fpso-orange";
    case "Procurement":
      return "border-l-yellow-400";
    case "Construction":
      return "border-l-fpso-blue";
    case "Commissioning":
    case "Delivery":
      return "border-l-fpso-green";
    default:
      return "border-l-fpso-muted";
  }
}

/* ------------------------------------------------------------------ */
/* Progress bar — 9 lifecycle segments                                 */
/* ------------------------------------------------------------------ */

/** Number of lit segments (0-9) for the phase progress bar. */
export function phaseProgressIndex(phase: string | null | undefined): number {
  if (!phase) return 0;
  const idx = PHASE_ORDER[phase];
  return idx == null ? 0 : idx + 1;
}

/** Segments for the 9-phase progress bar: label + lit color. */
export const PHASE_SEGMENTS = [
  { label: "Concept", color: "#64748b" },
  { label: "Planning", color: "#64748b" },
  { label: "Design", color: "#94a3b8" },
  { label: "Approval", color: "#ff9f43" },
  { label: "EPC", color: "#ff9f43" },
  { label: "Procurement", color: "#facc15" },
  { label: "Construction", color: "#00d4ff" },
  { label: "Commissioning", color: "#10b981" },
  { label: "Delivery", color: "#10b981" },
] as const;

export const PHASE_UNLIT = "var(--phase-unlit)";

/* ------------------------------------------------------------------ */
/* Legacy compatibility — reads old 4-value status data safely         */
/* ------------------------------------------------------------------ */

const LEGACY_STATUS_TO_PHASE: Record<string, string> = {
  "under construction": "Construction",
  construction: "Construction",
  delivered: "Delivery",
  completed: "Delivery",
  planned: "Planning",
  unknown: PHASE_UNKNOWN,
  "": PHASE_UNKNOWN,
};

/**
 * Transition helper: normalize a raw phase/status value into a canonical
 * phase label. Accepts both new phase names (validated) and legacy status
 * values ('Under Construction', 'Delivered', 'Planned'). Unknown input
 * returns null — callers fall back to PHASE_UNKNOWN for display.
 */
export function normalizePhase(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (PHASE_SET.has(trimmed)) return trimmed;
  const legacy = LEGACY_STATUS_TO_PHASE[trimmed.toLowerCase()];
  return legacy && legacy !== PHASE_UNKNOWN ? legacy : null;
}

/**
 * Read a phase from a raw Supabase row, tolerating both the new `phase`
 * column and the legacy `status` column (pre-migration rows / caches).
 */
export function phaseFromRow(row: Record<string, unknown>): string | null {
  const phase = row.phase;
  if (phase != null && String(phase).trim()) {
    return normalizePhase(String(phase));
  }
  return normalizePhase(String(row.status));
}

/** Display label for a phase value; null/unknown → PHASE_UNKNOWN. */
export function phaseLabel(phase: string | null | undefined): string {
  return phase ?? PHASE_UNKNOWN;
}
