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

export const PHASE_UNLIT = "#1e2844";

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

/* ------------------------------------------------------------------ */
/* Stage definitions — single source of truth for AI phase matching    */
/* ------------------------------------------------------------------ */

/**
 * Term definition for one lifecycle stage.
 *
 * These are the definitions the LLM reads when classifying a project's
 * phase. They are mirrored byte-for-byte in crawler/project_phase.py —
 * both sides render the SAME prompt block so the website and the crawler
 * never disagree about what a phase means. Change one, change the other
 * (scripts/check_stage_parity.sh fails the build otherwise).
 */
export interface StageDefinition {
  /** Canonical phase label — matches PHASES / PHASE_UNKNOWN. */
  phase: string;
  /** Chinese display name used in prompts and UI copy. */
  zh: string;
  /** 术语解释 — what this stage means. */
  definition: string;
  /** 典型特征 — what source text looks like at this stage. */
  characteristics: string;
  /** 事件关键词 — literal keywords to look for in the source text. */
  keywords: readonly string[];
  /** 业务含义 — what this stage means for the stainless-steel sales motion. */
  business: string;
}

/** The 10 standardized stages, in lifecycle order, Unknown last. */
export const STAGE_DEFINITIONS: readonly StageDefinition[] = [
  {
    phase: "Concept",
    zh: "概念",
    definition:
      "项目首次被提出，通常出现在政府规划、企业战略公告、媒体报道中，尚未形成具体建设计划。",
    characteristics:
      "只有意向性表述，无预算、无选址、无时间表；信息多来自政府规划文件、企业战略公告或媒体报道。",
    keywords: [
      "concept",
      "proposed",
      "under consideration",
      "feasibility study",
      "early stage",
    ],
    business: "无采购动作，仅作长期线索储备，不投入销售资源。",
  },
  {
    phase: "Planning",
    zh: "规划",
    definition:
      "项目进入正式规划阶段，明确了建设目标、大致规模、选址或开发方案，但尚未进入工程细节设计。",
    characteristics:
      "已有建设目标与大致规模（产能/投资额），可能已定选址，但无工程图纸与设备清单；常伴随可研报告、总体规划、环评启动。",
    keywords: [
      "planning",
      "master plan",
      "pre-FEED",
      "environmental impact assessment",
      "site selection",
    ],
    business: "仍无采购动作，可开始建立业主与设计院关系，争取进入合格供应商视野。",
  },
  {
    phase: "Design",
    zh: "设计",
    definition:
      "项目进入具体工程设计阶段，确定技术方案、工艺流程、设备选型和主要技术参数。",
    characteristics:
      "出现 FEED / 详细设计承包商、工艺流程、设备选型与技术规格书；材质等级与管道等级在此阶段被写死。",
    keywords: [
      "FEED",
      "detailed design",
      "engineering design",
      "technical specification",
      "design phase",
    ],
    business:
      "材质与规格在此阶段写入技术规格书，是进入合格供应商名录（AVL）并影响选材的关键窗口。",
  },
  {
    phase: "Approval",
    zh: "审批",
    definition:
      "项目通过政府审批、环境许可、投资决策或内部批准，正式确认推进。",
    characteristics:
      "出现明确的批文、许可证、环境许可或 FID（最终投资决策）通过；项目从「可能做」变为「确定做」。",
    keywords: [
      "approval",
      "permit",
      "consent",
      "FID",
      "final investment decision",
      "environmental permit",
    ],
    business: "项目落地确定性大幅提升，应锁定 EPC 竞标方名单，提前布局。",
  },
  {
    phase: "EPC Award",
    zh: "总包授标",
    definition: "项目业主与总承包商（EPC）签订合同，明确工程总包方。",
    characteristics:
      "出现总包合同签订、中标方名称、合同金额与工期；采购主体从业主转移到 EPC 承包商。",
    keywords: [
      "EPC award",
      "contract awarded",
      "contract signing",
      "EPC contractor selected",
    ],
    business: "采购主体确定，销售对象从业主转为 EPC 总包商，需立即建立联系。",
  },
  {
    phase: "Procurement",
    zh: "采购",
    definition:
      "EPC 承包商或业主启动设备和材料采购流程，包括询价、招标、评标和下单。",
    characteristics:
      "出现询价（RFQ）、招标、评标、订单（PO）、长周期设备定标等具体采购动作。",
    keywords: [
      "procurement",
      "tendering",
      "RFQ",
      "purchase order",
      "equipment supply",
    ],
    business: "核心商机窗口——询价、招标、下单都在此阶段发生，此时必须已在供应商名录内。",
  },
  {
    phase: "Construction",
    zh: "施工",
    definition:
      "项目进入现场施工阶段，设备安装、管道铺设、模块建造等实际工程开始。",
    characteristics:
      "出现开工、首钢切割、模块建造、设备安装、管道铺设等现场施工动作。",
    keywords: [
      "construction",
      "installation",
      "first steel cut",
      "construction started",
      "building phase",
    ],
    business: "主体长周期物资已定标，剩余机会为补充料、变更料与现场急件。",
  },
  {
    phase: "Commissioning",
    zh: "调试",
    definition:
      "项目主体完工后进行设备调试、系统联调、试运行，验证是否达到设计性能。",
    characteristics:
      "出现调试、联调、试运行、性能测试、机械竣工等验证性动作。",
    keywords: [
      "commissioning",
      "pre-commissioning",
      "start-up",
      "trial run",
      "performance test",
    ],
    business: "新增采购极少，机会集中在调试期更换件与备件。",
  },
  {
    phase: "Delivery",
    zh: "交付",
    definition: "项目正式交付给业主，进入生产或运营阶段。",
    characteristics:
      "出现交付、首油/首气、商业运营、移交业主等标志性节点。",
    keywords: [
      "delivery",
      "first oil",
      "first gas",
      "commercial operation",
      "handed over",
    ],
    business:
      "新建采购结束，转为售后备件与运维（MRO）机会，或作为同业主下一个项目的参考案例。",
  },
  {
    phase: PHASE_UNKNOWN,
    zh: "未知",
    definition: "原文信息不足，无法判断项目处于哪个阶段。",
    characteristics:
      "原文只提及项目名称或泛泛描述，没有任何生命周期动作词。",
    keywords: [],
    business: "需补充信息后再判断，不作为销售优先级依据。",
  },
] as const;

/** Lookup by canonical phase label. */
export const STAGE_DEFINITION_BY_PHASE: Record<string, StageDefinition> =
  Object.fromEntries(STAGE_DEFINITIONS.map((d) => [d.phase, d]));

/** Instructions that govern how the AI applies STAGE_DEFINITIONS. */
export const STAGE_MATCHING_RULES: readonly string[] = [
  "多个阶段同时出现时，取生命周期排序中最靠后的阶段（例如原文同时出现 contract awarded 与 procurement，取 Procurement）。",
  "优先依据原文明确出现的关键词判断，而不是笼统语境或行业常识推测。",
  "原文信息不足以支撑任何阶段时，阶段设为 Unknown（或 NULL），不要猜测。",
  "不得编造原文不存在的阶段证据；不追求 100% 准确，宁可返回 Unknown 也不要臆断。",
];

/**
 * Render the stage definitions as prompt text.
 *
 * MUST stay byte-identical to render_stage_definitions() in
 * crawler/project_phase.py.
 */
export function renderStageDefinitions(): string {
  const lines = ["【项目阶段术语定义（10 个标准阶段，按生命周期排序）】"];
  STAGE_DEFINITIONS.forEach((d, i) => {
    lines.push(`${i + 1}. ${d.phase}（${d.zh}）`);
    lines.push(`   定义: ${d.definition}`);
    lines.push(`   典型特征: ${d.characteristics}`);
    lines.push(
      `   关键词: ${d.keywords.length > 0 ? d.keywords.join(" | ") : "(无)"}`,
    );
    lines.push(`   业务含义: ${d.business}`);
  });
  return lines.join("\n");
}

/**
 * Render the matching rules as prompt text.
 *
 * MUST stay byte-identical to render_stage_matching_rules() in
 * crawler/project_phase.py.
 */
export function renderStageMatchingRules(): string {
  const lines = ["【阶段匹配规则】"];
  STAGE_MATCHING_RULES.forEach((rule, i) => {
    lines.push(`${i + 1}. ${rule}`);
  });
  return lines.join("\n");
}

/**
 * Full prompt block (definitions + rules) injected into every AI prompt
 * that reads or assigns a project phase.
 *
 * MUST stay byte-identical to stage_prompt_block() in
 * crawler/project_phase.py.
 */
export function stagePromptBlock(): string {
  return `${renderStageDefinitions()}\n\n${renderStageMatchingRules()}`;
}
