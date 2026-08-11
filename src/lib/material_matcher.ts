/**
 * FPSO Stainless Steel Material Matching Engine
 * ==============================================
 *
 * Rule-based engine that takes FPSO technical specifications
 * (water depth, capacity, hull type, field conditions) and
 * recommends stainless steel grades and application areas.
 *
 * All recommendations are heuristics based on industry practice.
 * Confidence levels reflect how many rules fired vs. available data.
 *
 * v2.0 — Factory capability integration:
 *   - Carbon steel grades are filtered out (factory does not produce CS)
 *   - Each recommended grade tagged with in_factory_scope boolean
 *   - can_manufacture() for grade-level producibility check
 *   - infer_product_needs() for equipment → product type inference
 *   - match_customer_type() for project → buyer profile matching
 */

import {
  isGradeProducible,
  isGradeExcluded,
  ProductType,
  TargetCustomerType,
  TARGET_CUSTOMER_KEYWORDS,
  EXCLUDED_CUSTOMER_KEYWORDS,
} from "@/data/factory_capabilities";

// ---- Types ---------------------------------------------------------------

export interface TechnicalSpecs {
  waterDepthM?: number | null;
  oilCapacityBpd?: number | null;
  gasCapacityMmcmd?: number | null;
  hullType?: string | null;
  fieldName?: string | null;
  operatorName?: string | null;
  basin?: string | null;
  // Optional: media parameters from article text
  hasH2S?: boolean;
  hasCO2?: boolean;
  hasHighTemp?: boolean;
  hasHighPressure?: boolean;
  /** Explicit sour service declaration (NACE MR0175 required). */
  sourService?: boolean;
  /** Raw corrosive_media JSON from DB for reasoning enrichment. */
  corrosiveMediaRaw?: Record<string, unknown> | null;
}

/** Per-grade annotation including factory scope. */
export interface GradeRecommendation {
  /** Grade name, e.g. "Duplex 2205". */
  grade: string;
  /** Whether this grade is within the factory's production capability. */
  in_factory_scope: boolean;
}

export interface MaterialMatchResult {
  /** Recommended stainless steel grades with factory scope annotation. */
  grades: GradeRecommendation[];
  /** Recommended application areas (equipment/components). */
  applications: string[];
  /** Confidence level: high (3+ rules fired), medium (1-2 rules), low (defaults only). */
  confidence: "high" | "medium" | "low";
  /** Human-readable reasoning chain. */
  reasoning: string;
  /** Grades that were excluded because factory cannot produce them (e.g., carbon steel). */
  excluded_grades: string[];
  /** Whether any recommended grades were filtered out. */
  factory_filtered: boolean;
}

/** Inferred product need from equipment description. */
export interface InferredProductNeed {
  /** Product type the project likely needs. */
  productType: ProductType;
  /** Human-readable Chinese label. */
  label: string;
  /** Confidence of the inference. */
  confidence: "high" | "medium" | "low";
  /** What triggered this inference (matched keyword/equipment). */
  trigger: string;
  /** Source of the inference — always "AI推断" for heuristic matches. */
  source: "AI推断";
}

/** Customer type match result. */
export interface CustomerTypeMatch {
  /** Whether this project matches a target customer type. */
  isTarget: boolean;
  /** Which target customer types were matched. */
  matchedTypes: TargetCustomerType[];
  /** Human-readable labels for matched types. */
  matchedLabels: string[];
  /** Whether non-target patterns were detected. */
  hasExclusion: boolean;
  /** Which exclusion types were matched. */
  exclusionTypes: string[];
}

// ---- Grade definitions ---------------------------------------------------

interface GradeInfo {
  name: string;
  category: string;
  description: string;
  /** Typical applications on FPSO */
  applications: string[];
}

const GRADES: Record<string, GradeInfo> = {
  "316L": {
    name: "316L",
    category: "Austenitic",
    description:
      "Standard austenitic stainless steel with 2-3% Mo. Good general corrosion resistance. Cost-effective for non-critical service.",
    applications: [
      "Process Piping (low-corrosion)",
      "Fresh Water Systems",
      "HVAC Ducting",
      "Handrails & Gratings",
      "Utility Piping",
    ],
  },
  "Duplex 2205": {
    name: "Duplex 2205",
    category: "Duplex",
    description:
      "22% Cr duplex stainless steel. High strength (2x 316L yield). Good SCC resistance. Widely used in offshore topsides.",
    applications: [
      "Process Piping",
      "Seawater Lift Pump",
      "Heat Exchangers",
      "Produced Water Treatment",
      "Mooring Components",
      "Cargo Oil Tanks (lining)",
    ],
  },
  "Super Duplex 2507": {
    name: "Super Duplex 2507",
    category: "Super Duplex",
    description:
      "25% Cr super duplex. Excellent pitting/crevice corrosion resistance (PREN >40). For deepwater high-pressure service.",
    applications: [
      "Subsea Manifolds",
      "Deepwater Risers",
      "Seawater Lift Pump (deep)",
      "High-Pressure Process Piping",
      "Gas Compression Coolers",
      "Mooring Systems (deepwater)",
    ],
  },
  "6Mo (UNS S31254)": {
    name: "6Mo (UNS S31254)",
    category: "Super Austenitic",
    description:
      "6% Mo super austenitic. Superior pitting resistance (PREN >43). For severe chloride environments and produced water.",
    applications: [
      "Produced Water Treatment",
      "Seawater Cooling Systems",
      "Heat Exchangers (seawater side)",
      "Chemical Injection Lines",
      "Flare Systems",
    ],
  },
  "904L": {
    name: "904L",
    category: "Austenitic",
    description:
      "High-alloy austenitic with Cu additions. Good resistance to reducing acids (H2SO4). For specific chemical service.",
    applications: [
      "Chemical Storage Tanks",
      "Acid Handling Systems",
      "Scrubbers",
      "Chemical Injection",
    ],
  },
  "Inconel 625": {
    name: "Inconel 625",
    category: "Nickel Alloy",
    description:
      "Ni-Cr-Mo alloy. Outstanding corrosion and high-temperature resistance. For the most demanding FPSO applications.",
    applications: [
      "Gas Compression (high-temp)",
      "Sour Service (H2S)",
      "Wellhead Components",
      "Subsea Trees",
      "Flare Tips",
    ],
  },
};

const ALL_GRADE_NAMES = Object.keys(GRADES);

// ---- Rule definitions ----------------------------------------------------

interface Rule {
  name: string;
  /** Returns true if the rule's condition is met */
  test: (specs: TechnicalSpecs) => boolean;
  /** Grades recommended when this rule fires */
  grades: string[];
  /** Applications recommended when this rule fires */
  applications: string[];
  /** Human-readable reason */
  reason: string;
}

const RULES: Rule[] = [
  // ===== Water Depth Rules =====
  {
    name: "ultra-deepwater",
    test: (s) => (s.waterDepthM ?? 0) > 2000,
    grades: ["Super Duplex 2507", "6Mo (UNS S31254)"],
    applications: [
      "Deepwater Risers",
      "Subsea Manifolds",
      "Seawater Lift Pump (deep)",
    ],
    reason:
      "Water depth >2000m: extreme external pressure requires Super Duplex 2507 or 6Mo for subsea equipment and risers.",
  },
  {
    name: "deepwater",
    test: (s) => (s.waterDepthM ?? 0) > 1500 && (s.waterDepthM ?? 0) <= 2000,
    grades: ["Super Duplex 2507"],
    applications: ["Seawater Lift Pump (deep)", "Subsea Manifolds"],
    reason:
      "Water depth >1500m: deepwater conditions recommend Super Duplex 2507 for seawater and subsea service.",
  },
  {
    name: "shallow-water",
    test: (s) =>
      s.waterDepthM != null && s.waterDepthM > 0 && s.waterDepthM <= 500,
    grades: ["Duplex 2205", "316L"],
    applications: ["Process Piping", "Seawater Lift Pump"],
    reason:
      "Water depth ≤500m: Duplex 2205 sufficient for moderate-depth service. 316L for non-critical piping.",
  },

  // ===== Oil Capacity Rules =====
  {
    name: "large-oil-capacity",
    test: (s) => (s.oilCapacityBpd ?? 0) > 150000,
    grades: ["Duplex 2205", "Super Duplex 2507"],
    applications: [
      "Cargo Oil Tanks",
      "Process Piping",
      "Heat Exchangers",
      "Produced Water Treatment",
    ],
    reason:
      "Oil capacity >150,000 bpd: large-scale topsides processing. Duplex/Super Duplex combo for process piping and cargo systems.",
  },
  {
    name: "medium-oil-capacity",
    test: (s) =>
      (s.oilCapacityBpd ?? 0) > 50000 && (s.oilCapacityBpd ?? 0) <= 150000,
    grades: ["Duplex 2205", "316L"],
    applications: ["Process Piping", "Cargo Oil Tanks"],
    reason:
      "Oil capacity 50k-150k bpd: mid-scale production. Duplex 2205 for critical piping, 316L for general service.",
  },

  // ===== Gas Capacity Rules =====
  {
    name: "high-gas-capacity",
    test: (s) => (s.gasCapacityMmcmd ?? 0) > 5,
    grades: ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
    applications: [
      "Gas Compression",
      "Gas Processing Piping",
      "Heat Exchangers",
      "Flare Systems",
    ],
    reason:
      "Gas capacity >5 MMcmd: high-volume gas processing. Corrosion-resistant alloys needed for compression and sweetening.",
  },
  {
    name: "moderate-gas-capacity",
    test: (s) =>
      (s.gasCapacityMmcmd ?? 0) > 1 && (s.gasCapacityMmcmd ?? 0) <= 5,
    grades: ["Duplex 2205", "Super Duplex 2507"],
    applications: ["Gas Compression", "Process Piping"],
    reason:
      "Gas capacity 1-5 MMcmd: moderate gas processing. Duplex 2205 or Super Duplex for compression piping.",
  },

  // ===== Hull Type Rules =====
  {
    name: "turret-mooring",
    test: (s) => {
      const ht = (s.hullType ?? "").toLowerCase();
      return ht.includes("turret") || ht.includes("internal turret") || ht.includes("external turret");
    },
    grades: ["Super Duplex 2507", "Duplex 2205"],
    applications: [
      "Mooring Systems",
      "Turret Bearing Components",
      "Swivel Stack",
    ],
    reason:
      "Turret mooring: high-stress rotating components require high-strength Duplex/Super Duplex stainless.",
  },
  {
    name: "spread-moored",
    test: (s) => {
      const ht = (s.hullType ?? "").toLowerCase();
      return ht.includes("spread") || ht.includes("spread moor");
    },
    grades: ["Duplex 2205"],
    applications: ["Mooring Components", "Fairleads", "Chain Stoppers"],
    reason:
      "Spread moored: Duplex 2205 sufficient for mooring components in spread-moor configuration.",
  },
  {
    name: "flng-conversion",
    test: (s) => {
      const ht = (s.hullType ?? "").toLowerCase();
      return ht.includes("flng") || ht.includes("lng") || ht.includes("conversion");
    },
    grades: ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
    applications: [
      "LNG Process Piping",
      "Cryogenic Heat Exchangers",
      "Gas Compression",
      "LNG Storage Tanks (lining)",
    ],
    reason:
      "FLNG/LNG conversion: cryogenic and gas processing requirements demand high-alloy stainless and nickel alloys.",
  },

  // ===== Media Parameter Rules (H2S, CO2, etc.) =====
  {
    name: "sour-service",
    test: (s) => s.hasH2S === true,
    grades: ["Super Duplex 2507", "Inconel 625"],
    applications: [
      "Gas Compression",
      "Sour Gas Piping",
      "Wellhead Components",
      "Production Separators",
    ],
    reason:
      "H2S present (sour service): NACE MR0175/ISO 15156 compliance required. Super Duplex 2507 and Inconel 625 for sour environments.",
  },
  {
    name: "co2-corrosion",
    test: (s) => s.hasCO2 === true,
    grades: ["Duplex 2205", "Super Duplex 2507"],
    applications: [
      "Process Piping",
      "Production Separators",
      "Heat Exchangers",
    ],
    reason:
      "CO2 present: carbonic acid corrosion risk. Duplex/Super Duplex grades offer superior CO2 corrosion resistance over 316L.",
  },
  {
    name: "sour-service-explicit",
    test: (s) => s.sourService === true,
    grades: ["Super Duplex 2507", "Inconel 625", "6Mo (UNS S31254)"],
    applications: [
      "Sour Gas Piping",
      "Gas Compression",
      "Production Separators",
      "Wellhead Components",
      "Chemical Injection Lines",
    ],
    reason:
      "Sour service explicitly declared: NACE MR0175/ISO 15156 compliance mandatory. Super Duplex 2507 for piping, Inconel 625 for critical wellhead/gas compression components. 316L NOT recommended for sour service.",
  },

  // ===== Basin Rules =====
  {
    name: "pre-salt-basin",
    test: (s) => {
      const basin = (s.basin ?? "").toLowerCase();
      return basin.includes("santos") || basin.includes("campos") || basin.includes("espirito");
    },
    grades: ["Super Duplex 2507", "6Mo (UNS S31254)", "Inconel 625"],
    applications: [
      "Subsea Manifolds",
      "Deepwater Risers",
      "Gas Compression",
      "Production Separators",
    ],
    reason:
      "Brazilian pre-salt basin: high CO2 content, deepwater, high-pressure. Requires premium corrosion-resistant alloys.",
  },
  {
    name: "west-africa-basin",
    test: (s) => {
      const basin = (s.basin ?? "").toLowerCase();
      return (
        basin.includes("niger delta") ||
        basin.includes("lower congo") ||
        basin.includes("kwanza") ||
        basin.includes("tano")
      );
    },
    grades: ["Duplex 2205", "Super Duplex 2507"],
    applications: ["Process Piping", "Cargo Oil Tanks", "Produced Water Treatment"],
    reason:
      "West Africa basin: moderate to deep water, variable H2S. Duplex/Super Duplex for process and cargo systems.",
  },

  // ===== Operator Rules (known requirements) =====
  {
    name: "petrobras-operator",
    test: (s) => {
      const op = (s.operatorName ?? "").toLowerCase();
      return op.includes("petrobras");
    },
    grades: ["Super Duplex 2507", "6Mo (UNS S31254)", "Duplex 2205"],
    applications: [
      "Subsea Manifolds",
      "Deepwater Risers",
      "Process Piping",
      "Gas Compression",
      "Produced Water Treatment",
    ],
    reason:
      "Petrobras operator: known pre-salt requirements. High CO2, deepwater, strict material specs per Petrobras standards.",
  },
  {
    name: "exxonmobil-operator",
    test: (s) => {
      const op = (s.operatorName ?? "").toLowerCase();
      return op.includes("exxon") || op.includes("exxonmobil");
    },
    grades: ["Duplex 2205", "Super Duplex 2507", "316L"],
    applications: [
      "Process Piping",
      "Cargo Oil Tanks",
      "Produced Water Treatment",
    ],
    reason:
      "ExxonMobil operator: GP3/GP(E) material specifications. Duplex 2205 for critical service, 316L for utility.",
  },
];

// ---- Default fallback ---------------------------------------------------

const DEFAULT_RESULT: MaterialMatchResult = {
  grades: [
    { grade: "316L", in_factory_scope: true },
    { grade: "Duplex 2205", in_factory_scope: true },
  ],
  applications: ["Process Piping", "Cargo Oil Tanks"],
  confidence: "low",
  reasoning:
    "Insufficient technical data for rule-based matching. Defaulting to 316L (general service) and Duplex 2205 (critical piping). Add water depth, capacity, or hull type for targeted recommendations.",
  excluded_grades: [],
  factory_filtered: false,
};

// ---- Engine --------------------------------------------------------------

/**
 * Match stainless steel grades and applications based on FPSO technical specs.
 *
 * Each matching rule that fires contributes grade and application recommendations.
 * Results are deduplicated and ranked by frequency. Carbon steel and other
 * excluded grades are filtered out. Each grade is annotated with the factory's
 * production capability status (in_factory_scope).
 *
 * @param specs - Technical specification fields. All nullable — only non-null
 *                values contribute to matching.
 * @returns Structured recommendation with grades, applications, confidence, and reasoning.
 */
export function matchMaterials(specs: TechnicalSpecs): MaterialMatchResult {
  const firedRules: Rule[] = [];

  for (const rule of RULES) {
    try {
      if (rule.test(specs)) {
        firedRules.push(rule);
      }
    } catch {
      // Skip rules that throw on unexpected input
    }
  }

  if (firedRules.length === 0) {
    return DEFAULT_RESULT;
  }

  // Aggregate grades and applications with frequency counting
  const gradeCounts = new Map<string, number>();
  const appCounts = new Map<string, number>();
  const reasons: string[] = [];

  for (const rule of firedRules) {
    for (const g of rule.grades) {
      gradeCounts.set(g, (gradeCounts.get(g) ?? 0) + 1);
    }
    for (const a of rule.applications) {
      appCounts.set(a, (appCounts.get(a) ?? 0) + 1);
    }
    reasons.push(rule.reason);
  }

  // Sort by frequency (descending), then alphabetically
  const sortedGrades = [...gradeCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name]) => name);

  // Filter out carbon steel and other excluded grades
  const excludedGrades: string[] = [];
  const keptGrades: string[] = [];
  for (const g of sortedGrades) {
    if (isGradeExcluded(g)) {
      excludedGrades.push(g);
    } else {
      keptGrades.push(g);
    }
  }

  const factoryFiltered = excludedGrades.length > 0;

  // If all grades were filtered out, fall back to default producible grades
  const finalGrades =
    keptGrades.length > 0 ? keptGrades : ["316L", "Duplex 2205"];

  // Build GradeRecommendation array with in_factory_scope annotation
  const gradeRecommendations: GradeRecommendation[] = finalGrades.map((g) => ({
    grade: g,
    in_factory_scope: isGradeProducible(g),
  }));

  const sortedApps = [...appCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name]) => name);

  // Confidence heuristic
  const dataPoints = [
    specs.waterDepthM,
    specs.oilCapacityBpd,
    specs.gasCapacityMmcmd,
    specs.hullType,
    specs.fieldName,
    specs.operatorName,
    specs.basin,
    specs.hasH2S !== undefined ? 1 : 0,
    specs.hasCO2 !== undefined ? 1 : 0,
    specs.sourService !== undefined ? 1 : 0,
  ].filter((v) => v != null && v !== "" && v !== 0).length;

  let confidence: "high" | "medium" | "low";
  if (firedRules.length >= 3 && dataPoints >= 3) {
    confidence = "high";
  } else if (firedRules.length >= 2) {
    confidence = "medium";
  } else {
    confidence = "low";
  }

  // Append factory filter note to reasoning
  let reasoning = reasons.join(" ");
  if (factoryFiltered) {
    reasoning +=
      ` [Factory filter: excluded ${excludedGrades.join(", ")} — not in production capability.]`;
  } else if (finalGrades.length > 0) {
    reasoning +=
      ` [Factory filter: all recommended grades are producible.]`;
  }

  // Append corrosive media summary if present
  const mediaFlags: string[] = [];
  if (specs.hasH2S) mediaFlags.push("H₂S detected");
  if (specs.hasCO2) mediaFlags.push("CO₂ detected");
  if (specs.sourService) mediaFlags.push("Sour service (NACE MR0175)");
  if (mediaFlags.length > 0) {
    reasoning +=
      ` [Corrosive media: ${mediaFlags.join(", ")}. Material selection accounts for corrosion resistance requirements.]`;
  }

  return {
    grades: gradeRecommendations,
    applications: sortedApps,
    confidence,
    reasoning,
    excluded_grades: excludedGrades,
    factory_filtered: factoryFiltered,
  };
}

/**
 * Convenience: run matching and return only the grade name strings.
 * For backward compatibility — returns flat string array.
 */
export function matchGrades(specs: TechnicalSpecs): string[] {
  return matchMaterials(specs).grades.map((g) => g.grade);
}

/**
 * Check whether the factory can manufacture a specific material grade.
 *
 * @param grade - Grade name string, e.g. "316L", "Duplex 2205", "A106 Gr B".
 * @returns true if the grade is within factory production capability.
 */
export function canManufacture(grade: string): boolean {
  return isGradeProducible(grade) && !isGradeExcluded(grade);
}

/**
 * Infer the product types a project likely needs based on its equipment
 * description or project type text.
 *
 * Uses keyword-based heuristics mapped to the factory's product catalog.
 * Results are tagged "AI推断" with medium confidence by default.
 *
 * @param description - Project description, equipment list, or scope text.
 * @returns Array of inferred product needs, deduplicated by product type.
 */
export function inferProductNeeds(description: string): InferredProductNeed[] {
  if (!description || description.trim().length === 0) return [];

  const lower = description.toLowerCase();
  const results: InferredProductNeed[] = [];

  // Define keyword → product type mappings
  const mappings: { keywords: string[]; productType: ProductType; label: string; defaultConfidence: "high" | "medium" | "low" }[] = [
    // Heat exchanger → tubes and pipes
    {
      keywords: ["heat exchanger", "shell and tube", "heater", "cooler", "condenser", "evaporator", "reboiler"],
      productType: "SEAMLESS_TUBE",
      label: "无缝管件",
      defaultConfidence: "high",
    },
    {
      keywords: ["heat exchanger", "heater", "cooler", "condenser"],
      productType: "SEAMLESS_PIPE",
      label: "无缝管",
      defaultConfidence: "medium",
    },
    // Flanges — direct keywords
    {
      keywords: [
        "flange", "connection", "joint", "spool",
        "pipeline connection", "tie-in", "subsea connection",
      ],
      productType: "FLANGES",
      label: "法兰",
      defaultConfidence: "high",
    },
    // Flanges — equipment that requires flanged connections
    {
      keywords: [
        "pump", "compressor", "centrifugal",
        "heat exchanger", "pressure vessel", "separator",
        "heater", "cooler", "condenser",
      ],
      productType: "FLANGES",
      label: "法兰",
      defaultConfidence: "high",
    },
    {
      keywords: ["pump", "compressor"],
      productType: "PIPE_FITTINGS",
      label: "管件",
      defaultConfidence: "medium",
    },
    // Riser / flowline → seamless pipe and coiled tubing
    {
      keywords: ["riser", "flowline", "pipeline", "export line", "infield line"],
      productType: "SEAMLESS_PIPE",
      label: "无缝管",
      defaultConfidence: "high",
    },
    {
      keywords: ["riser", "flowline", "coiled tubing", "intervention"],
      productType: "COILED_TUBING",
      label: "盘管",
      defaultConfidence: "medium",
    },
    // Water treatment / desalination → various
    {
      keywords: ["water treatment", "desalination", "reverse osmosis", "filtration", "produced water", "injection water"],
      productType: "SEAMLESS_TUBE",
      label: "无缝管件",
      defaultConfidence: "medium",
    },
    {
      keywords: ["water treatment", "desalination", "reverse osmosis", "produced water"],
      productType: "PIPE_FITTINGS",
      label: "管件",
      defaultConfidence: "medium",
    },
    // Structural / topsides → welded pipe
    {
      keywords: ["topsides", "deck", "hull", "structure", "platform", "jacket"],
      productType: "WELDED_PIPE",
      label: "焊管",
      defaultConfidence: "medium",
    },
    // Mooring → forged fittings
    {
      keywords: ["mooring", "anchor", "fairlead", "chain", "hawser"],
      productType: "FORGED_FITTINGS",
      label: "锻制管件",
      defaultConfidence: "medium",
    },
    // Subsea → various high-spec
    {
      keywords: ["subsea", "manifold", "tree", "wellhead", "xmas tree"],
      productType: "FORGED_FITTINGS",
      label: "锻制管件",
      defaultConfidence: "high",
    },
    {
      keywords: ["subsea", "manifold", "umbilical"],
      productType: "SEAMLESS_TUBE",
      label: "无缝管件",
      defaultConfidence: "medium",
    },
    // General piping references
    {
      keywords: ["pipe", "piping", "pipeline", "tubing"],
      productType: "SEAMLESS_PIPE",
      label: "无缝管",
      defaultConfidence: "low",
    },
    {
      keywords: ["pipe", "piping", "pipeline"],
      productType: "WELDED_PIPE",
      label: "焊管",
      defaultConfidence: "low",
    },
  ];

  for (const mapping of mappings) {
    for (const kw of mapping.keywords) {
      if (lower.includes(kw)) {
        // Check if this product type is already in results
        if (!results.some((r) => r.productType === mapping.productType)) {
          results.push({
            productType: mapping.productType,
            label: mapping.label,
            confidence: mapping.defaultConfidence,
            trigger: kw,
            source: "AI推断",
          });
        }
        break;
      }
    }
  }

  // Post-processing: if PIPE or TUBE is recommended, auto-add FLANGES.
  // Piping systems inherently require flanged connections.
  const PIPE_TUBE_TYPES: ProductType[] = [
    "SEAMLESS_PIPE",
    "WELDED_PIPE",
    "SEAMLESS_TUBE",
    "WELDED_TUBE",
  ];
  if (
    results.some((r) => PIPE_TUBE_TYPES.includes(r.productType)) &&
    !results.some((r) => r.productType === "FLANGES")
  ) {
    results.push({
      productType: "FLANGES",
      label: "法兰",
      confidence: "medium",
      trigger: "管道系统配套",
      source: "AI推断",
    });
  }

  return results;
}

/**
 * Match a project against the factory's target and excluded customer profiles.
 *
 * Analyzes project description, name, and equipment text to determine whether
 * the end customer is a good fit for the factory's ideal buyer profile.
 * Also checks for exclusion signals (small traders, stock clearances, etc.).
 *
 * @param projectText - Combined text from project name, description,
 *                      equipment scope, and any other contextual fields.
 * @returns Match result with boolean verdict and detailed type labels.
 */
export function matchCustomerType(projectText: string): CustomerTypeMatch {
  if (!projectText || projectText.trim().length === 0) {
    return {
      isTarget: false,
      matchedTypes: [],
      matchedLabels: [],
      hasExclusion: false,
      exclusionTypes: [],
    };
  }

  const lower = projectText.toLowerCase();

  // Check target customer type keywords
  const matchedTypes: TargetCustomerType[] = [];
  const matchedLabels: string[] = [];

  for (const [typeKey, keywords] of Object.entries(TARGET_CUSTOMER_KEYWORDS)) {
    const matched = keywords.some((kw) => lower.includes(kw.toLowerCase()));
    if (matched) {
      matchedTypes.push(typeKey as TargetCustomerType);
      const labelMap: Record<string, string> = {
        HEAT_EXCHANGER_MANUFACTURER: "换热器制造商",
        SS_PIPE_DISTRIBUTOR: "不锈钢管分销商",
        WATER_TREATMENT_EPC: "水处理方案商",
        OFFSHORE_PLATFORM_EPC: "海上钻井平台方案商",
      };
      matchedLabels.push(labelMap[typeKey] ?? typeKey);
    }
  }

  // Check exclusion keywords
  const exclusionTypes: string[] = [];
  for (const [exclKey, keywords] of Object.entries(EXCLUDED_CUSTOMER_KEYWORDS)) {
    const matched = keywords.some((kw) => lower.includes(kw.toLowerCase()));
    if (matched) {
      exclusionTypes.push(exclKey);
    }
  }

  const isTarget = matchedTypes.length > 0 && exclusionTypes.length === 0;
  const hasExclusion = exclusionTypes.length > 0;

  return {
    isTarget,
    matchedTypes,
    matchedLabels,
    hasExclusion,
    exclusionTypes,
  };
}

/**
 * Parse a raw recommendation_json value back into a MaterialMatchResult.
 * Handles both legacy format (grades: string[]) and v2 format (grades: GradeRecommendation[]).
 * Returns null if the JSON is missing or malformed.
 */
export function parseRecommendation(
  json: string | null | undefined,
): MaterialMatchResult | null {
  if (!json) return null;
  try {
    const parsed = JSON.parse(json);
    if (
      Array.isArray(parsed.grades) &&
      Array.isArray(parsed.applications) &&
      typeof parsed.confidence === "string" &&
      typeof parsed.reasoning === "string"
    ) {
      // Normalize grades: legacy string[] → GradeRecommendation[]
      const normalizedGrades: GradeRecommendation[] = parsed.grades.map(
        (g: string | GradeRecommendation) => {
          if (typeof g === "string") {
            return {
              grade: g,
              in_factory_scope: isGradeProducible(g),
            };
          }
          return {
            grade: g.grade,
            in_factory_scope: g.in_factory_scope ?? isGradeProducible(g.grade),
          };
        },
      );

      return {
        grades: normalizedGrades,
        applications: parsed.applications,
        confidence: parsed.confidence,
        reasoning: parsed.reasoning,
        excluded_grades: parsed.excluded_grades ?? [],
        factory_filtered: parsed.factory_filtered ?? false,
      };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Build TechnicalSpecs from a raw Supabase row (snake_case columns).
 */
export function specsFromRow(row: Record<string, unknown>): TechnicalSpecs {
  const toNum = (v: unknown): number | null => {
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const toStr = (v: unknown): string | null => {
    if (v == null || v === "") return null;
    return String(v).trim() || null;
  };

  // Parse corrosive_media JSONB column if present
  let hasH2S: boolean | undefined;
  let hasCO2: boolean | undefined;
  let sourService: boolean | undefined;
  let corrosiveMediaRaw: Record<string, unknown> | null = null;

  const cmRaw = row.corrosive_media;
  if (cmRaw && typeof cmRaw === "object" && !Array.isArray(cmRaw)) {
    corrosiveMediaRaw = cmRaw as Record<string, unknown>;
    if (typeof corrosiveMediaRaw.h2s === "boolean") hasH2S = corrosiveMediaRaw.h2s;
    if (typeof corrosiveMediaRaw.co2 === "boolean") hasCO2 = corrosiveMediaRaw.co2;
    if (typeof corrosiveMediaRaw.sour_service === "boolean") sourService = corrosiveMediaRaw.sour_service;
  } else if (typeof cmRaw === "string" && cmRaw.trim()) {
    try {
      const parsed = JSON.parse(cmRaw);
      if (parsed && typeof parsed === "object") {
        corrosiveMediaRaw = parsed;
        if (typeof parsed.h2s === "boolean") hasH2S = parsed.h2s;
        if (typeof parsed.co2 === "boolean") hasCO2 = parsed.co2;
        if (typeof parsed.sour_service === "boolean") sourService = parsed.sour_service;
      }
    } catch {
      // Ignore malformed JSON
    }
  }

  return {
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    hasH2S,
    hasCO2,
    sourService,
    corrosiveMediaRaw,
  };
}

// ---- Corrosive Media Display Helpers ---------------------------------------

/** A single corrosive media tag for UI display. */
export interface CorrosiveMediaTag {
  label: string;
  className: string;
  key: string;
}

/**
 * Parse raw corrosive_media column value (JSONB object or JSON string).
 * Returns parsed object or null on failure.
 */
export function parseCorrosiveMedia(raw: unknown): Record<string, unknown> | null {
  if (!raw) return null;
  if (typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw === "string" && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch {
      // ignore malformed JSON
    }
  }
  return null;
}

/**
 * Extract display tags from parsed corrosive_media data.
 * Returns empty array if no media flags are set.
 */
export function getCorrosiveMediaTags(
  cm: Record<string, unknown> | null | undefined,
): CorrosiveMediaTag[] {
  if (!cm) return [];
  const tags: CorrosiveMediaTag[] = [];
  if (cm.h2s === true) {
    tags.push({ label: "H₂S", className: "border-red-500/50 text-red-400", key: "h2s" });
  }
  if (cm.co2 === true) {
    tags.push({ label: "CO₂", className: "border-yellow-500/50 text-yellow-400", key: "co2" });
  }
  if (cm.sour_service === true) {
    tags.push({ label: "Sour Service", className: "border-rose-500/50 text-rose-400", key: "sour" });
  }
  if (cm.chloride === true) {
    tags.push({ label: "Cl⁻", className: "border-blue-500/50 text-blue-400", key: "chloride" });
  }
  return tags;
}

/**
 * Extract human-readable details string from corrosive_media data.
 * Returns null if no details field present.
 */
export function getCorrosiveMediaDetails(
  cm: Record<string, unknown> | null | undefined,
): string | null {
  if (!cm) return null;
  const d = cm.details;
  if (typeof d === "string" && d.trim()) return d.trim();
  return null;
}

/**
 * Check if a TechnicalSpecs has any meaningful data.
 */
export function hasAnySpecs(specs: TechnicalSpecs): boolean {
  return (
    specs.waterDepthM != null ||
    specs.oilCapacityBpd != null ||
    specs.gasCapacityMmcmd != null ||
    (specs.hullType != null && specs.hullType !== "") ||
    (specs.fieldName != null && specs.fieldName !== "") ||
    (specs.operatorName != null && specs.operatorName !== "") ||
    (specs.basin != null && specs.basin !== "") ||
    specs.hasH2S != null ||
    specs.hasCO2 != null ||
    specs.sourService != null
  );
}

// ---- Procurement Timeline Estimation -------------------------------------

/** Result of procurement window estimation. */
export interface ProcurementWindowResult {
  /** ISO date string of estimated procurement start (YYYY-MM-DD). */
  estimated_date: string;
  /** Confidence of the estimate. */
  confidence: "high" | "medium" | "low";
  /** Human-readable reasoning chain. */
  reasoning: string;
}

/**
 * Minimal project shape needed by `estimateProcurementWindow`.
 * Accepts both the full Project type and partial objects.
 */
export interface ProcurementProjectInput {
  name?: string;
  status?: string;
  summary?: string;
  industry?: string;
  source?: { date?: string };
  createdAt?: string | null;
}

/**
 * A single timeline milestone (minimal shape).
 * Pass timeline events from candidate_events to improve estimate accuracy.
 */
export interface ProcurementTimelineEvent {
  eventType?: string;
  publicationDate?: string;
}

/**
 * Estimate when a project will enter its stainless steel procurement window.
 *
 * Heuristics based on FPSO industry procurement patterns:
 *   - FID + 6 months is typical start for long-lead equipment inquiries
 *   - Construction start → bulk piping procurement follows within 3-6 months
 *   - Earlier phases (EIA/FEED) → window is further out (12-18 months)
 *
 * Confidence is higher when timeline events (FPSO_CONTRACT_AWARDED) are
 * available; lower when only status-based inference is possible.
 *
 * @param project - Project data (status, summary, name, etc.).
 * @param timelineEvents - Optional timeline milestones from candidate_events.
 * @returns Estimated procurement window with date, confidence, and reasoning.
 */
export function estimateProcurementWindow(
  project: ProcurementProjectInput,
  timelineEvents?: ProcurementTimelineEvent[],
): ProcurementWindowResult {
  const now = new Date();
  const status = (project.status ?? "").trim();
  const summary = (project.summary ?? "").toLowerCase();
  const name = (project.name ?? "").toLowerCase();
  const combined = summary + " " + name;

  // ---- Rule 1: FPSO_CONTRACT_AWARDED timeline event → high-confidence estimate ----
  const contractEvent = timelineEvents?.find(
    (e) => (e.eventType ?? "").toUpperCase() === "FPSO_CONTRACT_AWARDED",
  );
  if (contractEvent?.publicationDate) {
    const contractDate = new Date(contractEvent.publicationDate);
    if (!isNaN(contractDate.getTime())) {
      // Procurement starts 2-4 months after contract award (mid-point: 3 months)
      const estDate = new Date(contractDate);
      estDate.setMonth(estDate.getMonth() + 3);
      return {
        estimated_date: estDate.toISOString().slice(0, 10),
        confidence: "high",
        reasoning:
          `FPSO contract awarded on ${contractEvent.publicationDate.slice(0, 10)}. ` +
          `Long-lead equipment procurement typically begins 2-4 months post-award. ` +
          `Estimated window opens ${estDate.toISOString().slice(0, 10)}.`,
      };
    }
  }

  // ---- Rule 2: Under Construction → imminent procurement (3-6 months) ----
  if (status === "Under Construction") {
    const estDate = new Date(now);
    estDate.setMonth(estDate.getMonth() + 4); // mid-point of 3-6 months
    return {
      estimated_date: estDate.toISOString().slice(0, 10),
      confidence: "medium",
      reasoning:
        "Project is Under Construction. Bulk piping and fittings procurement " +
        "typically occurs during construction phase. Estimated window: 3-6 months. " +
        "Urgent needs may be sooner — contact EPC contractor to confirm schedule.",
    };
  }

  // ---- Rule 3: Planned + FEED/FID phase → 6-12 months ----
  if (status === "Planned") {
    const isFeed =
      combined.includes("feed") ||
      combined.includes("front end") ||
      combined.includes("fid") ||
      combined.includes("final investment");
    const isEia =
      combined.includes("eia") ||
      combined.includes("environmental") ||
      combined.includes("pre-feed") ||
      combined.includes("conceptual") ||
      combined.includes("feasibility");

    if (isFeed) {
      const estDate = new Date(now);
      estDate.setMonth(estDate.getMonth() + 9); // mid-point of 6-12 months
      return {
        estimated_date: estDate.toISOString().slice(0, 10),
        confidence: "medium",
        reasoning:
          "Project is Planned with FEED/FID phase detected. FID typically triggers " +
          "long-lead equipment procurement within 6-12 months. Estimated window: " +
          `${estDate.toISOString().slice(0, 10)}. Monitor for FID announcement.`,
      };
    }

    if (isEia) {
      const estDate = new Date(now);
      estDate.setMonth(estDate.getMonth() + 15); // mid-point of 12-18 months
      return {
        estimated_date: estDate.toISOString().slice(0, 10),
        confidence: "low",
        reasoning:
          "Project is in early planning / EIA phase. Procurement window likely " +
          "12-18 months out. Re-evaluate when project reaches FEED or FID. " +
          `Estimated window: ${estDate.toISOString().slice(0, 10)}.`,
      };
    }

    // Planned but no phase detected → FPSO default
    const isFpso = (project.industry ?? "").toUpperCase() === "FPSO";
    const estDate = new Date(now);
    estDate.setMonth(estDate.getMonth() + (isFpso ? 9 : 12));
    return {
      estimated_date: estDate.toISOString().slice(0, 10),
      confidence: "low",
      reasoning:
        isFpso
          ? "Planned FPSO project. Industry norm: long-lead equipment procurement " +
            "begins ~6 months post-FID. Without confirmed FID date, estimating " +
            `${estDate.toISOString().slice(0, 10)}. Monitor for FID announcement.`
          : "Planned project without detailed phase data. Conservative estimate: " +
            `12 months out (${estDate.toISOString().slice(0, 10)}). ` +
            "Add timeline data for higher-confidence estimate.",
    };
  }

  // ---- Rule 4: Delivered / complete → retrospective, no active window ----
  if (status === "Delivered" || status === "Completed") {
    return {
      estimated_date: "N/A",
      confidence: "high",
      reasoning:
        "Project is already delivered/completed. Procurement window has passed. " +
        "Consider targeting MRO (maintenance, repair, operations) spares instead.",
    };
  }

  // ---- Rule 5: Unknown status → FPSO default heuristic ----
  const isFpso = (project.industry ?? "").toUpperCase() === "FPSO";
  const estDate = new Date(now);
  estDate.setMonth(estDate.getMonth() + 6);
  return {
    estimated_date: estDate.toISOString().slice(0, 10),
    confidence: "low",
    reasoning:
      isFpso
        ? "Insufficient project data for precise estimation. FPSO industry default: " +
          "long-lead equipment procurement typically starts ~6 months post-FID. " +
          `Conservative estimate: ${estDate.toISOString().slice(0, 10)}. ` +
          "Add status and timeline data for higher-confidence estimate."
        : "Insufficient project data. Conservative estimate: 6 months from today. " +
          "Add status, phase, and timeline events for higher-confidence estimate.",
  };
}
