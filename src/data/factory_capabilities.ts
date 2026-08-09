/**
 * Factory Capability Matrix — 嘉兴 MT 不锈钢 (Jiaxing MT Stainless Steel)
 * =====================================================================
 *
 * Defines the full product, material, and customer-scope capabilities
 * of the factory. Used by the material matcher and opportunity-matching
 * engine to filter recommendations to only what the factory can produce,
 * and to qualify projects against target customer profiles.
 *
 * All enums and constants are the single source of truth. When the
 * factory adds or drops a product line, update ONLY this file.
 */

// ---- Product Type Enum ---------------------------------------------------

/** Product types the factory can manufacture. */
export const PRODUCT_TYPES = [
  "SEAMLESS_PIPE",
  "WELDED_PIPE",
  "SEAMLESS_TUBE",
  "WELDED_TUBE",
  "PIPE_FITTINGS",
  "FORGED_FITTINGS",
  "CAST_FITTINGS",
  "FLANGES",
  "COILED_TUBING",
  "STEEL_WIRE",
] as const;

export type ProductType = (typeof PRODUCT_TYPES)[number];

/** Human-readable Chinese labels for each product type. */
export const PRODUCT_TYPE_LABELS: Record<ProductType, string> = {
  SEAMLESS_PIPE: "无缝管",
  WELDED_PIPE: "焊管",
  SEAMLESS_TUBE: "无缝管件",
  WELDED_TUBE: "焊接管件",
  PIPE_FITTINGS: "管件",
  FORGED_FITTINGS: "锻制管件",
  CAST_FITTINGS: "铸造管件",
  FLANGES: "法兰",
  COILED_TUBING: "盘管",
  STEEL_WIRE: "线材",
};

// ---- Material Grade Classifications --------------------------------------

/** Materials the factory CAN produce, grouped by category. */
export interface MaterialCategory {
  /** Category name (Stainless Steel / Duplex Steel / Nickel Alloy). */
  category: string;
  /** Specific grade designations under this category. */
  grades: string[];
}

/** Factory-producible material categories with exact grade lists. */
export const PRODUCIBLE_MATERIALS: MaterialCategory[] = [
  {
    category: "Stainless Steel (Austenitic)",
    grades: [
      "304",
      "304L",
      "304H",
      "316",
      "316L",
      "316H",
      "316Ti",
      "317L",
      "321",
      "321H",
      "347",
      "347H",
      "904L",
      "309S",
      "310S",
    ],
  },
  {
    category: "Duplex Steel",
    grades: [
      "Duplex 2205",
      "Super Duplex 2507",
      "Lean Duplex 2304",
      "Lean Duplex 2101",
      "Zeron 100",
      "S32760",
    ],
  },
  {
    category: "Nickel Alloy",
    grades: [
      "Inconel 625",
      "Inconel 825",
      "Incoloy 800",
      "Incoloy 800H",
      "Incoloy 800HT",
      "Incoloy 825",
      "Hastelloy C276",
      "Hastelloy C22",
      "Monel 400",
      "Monel K500",
      "6Mo (UNS S31254)",
      "Alloy 20",
      "254SMO",
      "UNS N08926",
    ],
  },
];

/** Materials the factory absolutely CANNOT produce. */
export const EXCLUDED_MATERIALS: MaterialCategory[] = [
  {
    category: "Carbon Steel",
    grades: [
      "A106 Gr B",
      "A53 Gr B",
      "API 5L X42",
      "API 5L X52",
      "API 5L X60",
      "API 5L X65",
      "API 5L X70",
      "A333 Gr 6",
      "A333 Gr 3",
      "A335 P11",
      "A335 P22",
      "A335 P91",
      "SA516 Gr 70",
      "SA516 Gr 60",
      "A105",
      "A234 WPB",
      "A350 LF2",
      "A420 WPL6",
    ],
  },
];

// ---- Flat lookup sets (derived, kept in sync manually) ---------------------

/** All grades the factory can produce, as a flat Set for O(1) lookup. */
export const PRODUCIBLE_GRADE_SET: Set<string> = new Set(
  PRODUCIBLE_MATERIALS.flatMap((c) => c.grades),
);

/** All grades the factory cannot produce (e.g., carbon steel), flat Set. */
export const EXCLUDED_GRADE_SET: Set<string> = new Set(
  EXCLUDED_MATERIALS.flatMap((c) => c.grades),
);

/** All producible grade names in a flat array (for iteration). */
export const ALL_PRODUCIBLE_GRADES: string[] = [...PRODUCIBLE_GRADE_SET];

/** All excluded grade names in a flat array. */
export const ALL_EXCLUDED_GRADES: string[] = [...EXCLUDED_GRADE_SET];

// ---- Customer Targeting ---------------------------------------------------

/** Target customer types (ideal buyer profiles). */
export const TARGET_CUSTOMER_TYPES = [
  "HEAT_EXCHANGER_MANUFACTURER",
  "SS_PIPE_DISTRIBUTOR",
  "WATER_TREATMENT_EPC",
  "OFFSHORE_PLATFORM_EPC",
] as const;

export type TargetCustomerType = (typeof TARGET_CUSTOMER_TYPES)[number];

/** Labels for target customer types. */
export const TARGET_CUSTOMER_LABELS: Record<TargetCustomerType, string> = {
  HEAT_EXCHANGER_MANUFACTURER: "换热器制造商",
  SS_PIPE_DISTRIBUTOR: "不锈钢管分销商",
  WATER_TREATMENT_EPC: "水处理方案商",
  OFFSHORE_PLATFORM_EPC: "海上钻井平台方案商",
};

/** Keywords that signal a project is from a TARGET customer type. */
export const TARGET_CUSTOMER_KEYWORDS: Record<TargetCustomerType, string[]> = {
  HEAT_EXCHANGER_MANUFACTURER: [
    "heat exchanger",
    "heater",
    "cooler",
    "condenser",
    "evaporator",
    "reboiler",
    "boiler",
    "thermal",
    "hvac",
    "shell and tube",
    "plate heat",
  ],
  SS_PIPE_DISTRIBUTOR: [
    "distributor",
    "wholesale",
    "supplier",
    "stockist",
    "pipe distributor",
    "tube distributor",
    "steel distributor",
    "stainless distributor",
  ],
  WATER_TREATMENT_EPC: [
    "water treatment",
    "desalination",
    "reverse osmosis",
    "wastewater",
    "sewage",
    "filtration",
    "purification",
    "water plant",
    "effluent",
    "swro",
    "mfro",
    "produced water",
    "injection water",
    "water injection",
  ],
  OFFSHORE_PLATFORM_EPC: [
    "fpso",
    "flng",
    "offshore platform",
    "jacket",
    "topsides",
    "subsea",
    "deepwater",
    "offshore",
    "drilling",
    "riser",
    "flowline",
    "umbilical",
    "mooring",
    "fpso project",
    "fpso construction",
    "fpso conversion",
  ],
};

/** Non-target customer types (projects from these should be deprioritized). */
export const EXCLUDED_CUSTOMER_TYPES = [
  "TRADING_COMPANY",
  "STOCK_INVENTORY",
  "INDIVIDUAL_RESELLER",
  "LOW_VOLUME",
] as const;

export type ExcludedCustomerType = (typeof EXCLUDED_CUSTOMER_TYPES)[number];

/** Labels for excluded customer types. */
export const EXCLUDED_CUSTOMER_LABELS: Record<ExcludedCustomerType, string> = {
  TRADING_COMPANY: "小型贸易公司",
  STOCK_INVENTORY: "库存商",
  INDIVIDUAL_RESELLER: "个人转售",
  LOW_VOLUME: "小批量批发",
};

/** Keywords that signal a project is from a NON-TARGET customer type. */
export const EXCLUDED_CUSTOMER_KEYWORDS: Record<ExcludedCustomerType, string[]> = {
  TRADING_COMPANY: [
    "trading company",
    "trading house",
    "general trading",
    "commodity trader",
    "export trading",
    "import trading",
  ],
  STOCK_INVENTORY: [
    "in stock",
    "stock lot",
    "inventory clearance",
    "surplus stock",
    "available from stock",
    "ready stock",
    "warehouse stock",
    "ex stock",
  ],
  INDIVIDUAL_RESELLER: [
    "individual buyer",
    "personal purchase",
    "reseller",
    "middleman",
    "broker",
    "agent only",
    "commission agent",
    "sourcing agent",
  ],
  LOW_VOLUME: [
    "small quantity",
    "sample order",
    "trial order",
    "low volume",
    "small order",
    "moq",
    "minimum order",
    "少量",
    "小批量",
    "样品",
  ],
};

// ---- Factory Capability Record (detailed per-grade) -----------------------

export interface FactoryCapability {
  /** Grade name, e.g. "316L", "Duplex 2205". */
  grade: string;
  /** Whether the factory can produce this grade. */
  canProduce: boolean;
  /** Maximum pipe/tube size the factory can produce in this grade. */
  maxSize?: string;
  /** Available wall-thickness schedules. */
  schedule?: string;
  /** Product forms available for this grade. */
  productTypes: ProductType[];
  /** Additional notes (lead time, quantity limits, etc.). */
  notes?: string;
}

/**
 * Detailed per-grade factory capabilities.
 *
 * When `canProduce` is false, productTypes is empty and notes explains why.
 * This is the authoritative record — all filtering functions read from this.
 */
export const FACTORY_CAPABILITIES: FactoryCapability[] = [
  // ---- Austenitic Stainless (all producible) ----
  {
    grade: "304",
    canProduce: true,
    maxSize: "24 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "WELDED_TUBE", "PIPE_FITTINGS", "FLANGES", "STEEL_WIRE"],
  },
  {
    grade: "304L",
    canProduce: true,
    maxSize: "24 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "WELDED_TUBE", "PIPE_FITTINGS", "FLANGES"],
  },
  {
    grade: "304H",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High-carbon variant — limited stock, 6-8 week lead time.",
  },
  {
    grade: "316",
    canProduce: true,
    maxSize: "24 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "WELDED_TUBE", "PIPE_FITTINGS", "FLANGES", "STEEL_WIRE"],
  },
  {
    grade: "316L",
    canProduce: true,
    maxSize: "24 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S, SCH 160",
    productTypes: [
      "SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "WELDED_TUBE",
      "PIPE_FITTINGS", "FORGED_FITTINGS", "FLANGES", "COILED_TUBING", "STEEL_WIRE",
    ],
  },
  {
    grade: "316H",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High-carbon variant — limited stock.",
  },
  {
    grade: "316Ti",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Titanium-stabilized — made to order, 8-12 week lead time.",
  },
  {
    grade: "317L",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Higher Mo content (3-4%) — limited production runs.",
  },
  {
    grade: "321",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
  },
  {
    grade: "321H",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High-carbon variant — limited stock.",
  },
  {
    grade: "347",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
  },
  {
    grade: "347H",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High-carbon variant — limited stock.",
  },
  {
    grade: "904L",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High-alloy austenitic — made to order, 10-14 week lead time.",
  },
  {
    grade: "309S",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Heat-resistant grade — limited production.",
  },
  {
    grade: "310S",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Heat-resistant grade — limited production.",
  },

  // ---- Duplex Steel (all producible) ----
  {
    grade: "Duplex 2205",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "WELDED_TUBE", "PIPE_FITTINGS", "FORGED_FITTINGS", "FLANGES", "COILED_TUBING"],
  },
  {
    grade: "Super Duplex 2507",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FORGED_FITTINGS", "FLANGES"],
    notes: "Limited quantity — 12-16 week lead time. PREN >40 material.",
  },
  {
    grade: "Lean Duplex 2304",
    canProduce: true,
    maxSize: "16 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "WELDED_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Economy duplex alternative to 316L — growing demand.",
  },
  {
    grade: "Lean Duplex 2101",
    canProduce: true,
    maxSize: "12 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Limited production runs.",
  },
  {
    grade: "Zeron 100",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Super duplex alternative — limited quantity, 14-18 week lead time.",
  },
  {
    grade: "S32760",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Super duplex with W — limited quantity.",
  },

  // ---- Nickel Alloy (most producible) ----
  {
    grade: "Inconel 625",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Premium nickel alloy — made to order, 16-20 week lead time.",
  },
  {
    grade: "Inconel 825",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Made to order, 14-18 week lead time.",
  },
  {
    grade: "Incoloy 800",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Made to order, 12-16 week lead time.",
  },
  {
    grade: "Incoloy 800H",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "High-carbon variant — made to order.",
  },
  {
    grade: "Incoloy 800HT",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Made to order, 12-16 week lead time.",
  },
  {
    grade: "Incoloy 825",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Made to order, 14-18 week lead time.",
  },
  {
    grade: "Hastelloy C276",
    canProduce: true,
    maxSize: "6 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Premium corrosion-resistant alloy — made to order, 18-22 week lead time.",
  },
  {
    grade: "Hastelloy C22",
    canProduce: true,
    maxSize: "6 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Made to order, 18-22 week lead time.",
  },
  {
    grade: "Monel 400",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Ni-Cu alloy — made to order, 14-18 week lead time.",
  },
  {
    grade: "Monel K500",
    canProduce: true,
    maxSize: "6 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Age-hardenable Monel — limited production, 16-20 week lead time.",
  },
  {
    grade: "6Mo (UNS S31254)",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "Super austenitic 6% Mo — made to order, 12-16 week lead time.",
  },
  {
    grade: "Alloy 20",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS"],
    notes: "Ni-Fe-Cr alloy for sulfuric acid service — made to order.",
  },
  {
    grade: "254SMO",
    canProduce: true,
    maxSize: "10 inch",
    schedule: "SCH 10S, SCH 40S, SCH 80S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "High Mo super austenitic — made to order, 12-16 week lead time.",
  },
  {
    grade: "UNS N08926",
    canProduce: true,
    maxSize: "8 inch",
    schedule: "SCH 10S, SCH 40S",
    productTypes: ["SEAMLESS_PIPE", "SEAMLESS_TUBE", "PIPE_FITTINGS", "FLANGES"],
    notes: "6Mo equivalent — limited production.",
  },

  // ---- CARBON STEEL — factory explicitly CANNOT produce ----
  {
    grade: "Carbon Steel (any grade)",
    canProduce: false,
    productTypes: [],
    notes: "Factory does not produce carbon steel. Absolute exclusion per company policy.",
  },
];

// ---- Derived lookup maps --------------------------------------------------

/** Map from grade name to its FactoryCapability record. */
export const CAPABILITY_BY_GRADE: Map<string, FactoryCapability> = new Map(
  FACTORY_CAPABILITIES.map((c) => [c.grade, c]),
);

/** Set of product types the factory can produce (all). */
export const PRODUCIBLE_PRODUCT_TYPES: Set<ProductType> = new Set(
  FACTORY_CAPABILITIES
    .filter((c) => c.canProduce)
    .flatMap((c) => c.productTypes),
);

/**
 * Check if a given grade name is within factory production capability.
 * Handles partial matches (e.g., "316L stainless steel" → matches "316L").
 */
export function isGradeProducible(gradeName: string): boolean {
  const normalized = gradeName.trim();
  // Direct lookup
  if (PRODUCIBLE_GRADE_SET.has(normalized)) return true;
  // Check if any producible grade appears as a substring
  for (const g of PRODUCIBLE_GRADE_SET) {
    if (normalized.includes(g)) return true;
  }
  return false;
}

/**
 * Check if a given grade name is explicitly excluded (e.g., carbon steel).
 */
export function isGradeExcluded(gradeName: string): boolean {
  const normalized = gradeName.trim();
  if (EXCLUDED_GRADE_SET.has(normalized)) return true;
  for (const g of EXCLUDED_GRADE_SET) {
    if (normalized.includes(g)) return true;
  }
  // Broad catch: any mention of "carbon steel", "carbon", "CS", "LTCS"
  const lower = normalized.toLowerCase();
  if (
    lower.includes("carbon steel") ||
    lower.includes("carbon") ||
    lower === "cs" ||
    lower.includes("a106") ||
    lower.includes("a53") ||
    lower.includes("api 5l") ||
    lower.includes("a333") ||
    lower.includes("a335") ||
    lower.includes("sa516") ||
    lower.includes("a105") ||
    lower.includes("a234") ||
    lower.includes("a350") ||
    lower.includes("a420")
  ) {
    return true;
  }
  return false;
}
