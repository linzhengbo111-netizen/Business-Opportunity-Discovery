/**
 * Opportunity Scoring Engine (S5)
 * ================================
 *
 * 5-dimension quantitative scoring model that transforms raw project data
 * into prioritized sales opportunities. Scores range 0-100 across:
 *   - Procurement Probability (0-20)
 *   - Factory Match (0-20)
 *   - Reachability (0-20)
 *   - Project Value (0-20)
 *   - Information Confidence (0-20)
 *
 * Grade thresholds: A >= 80, B >= 60, C >= 40, D < 40
 */

import type { Project } from "@/data/projects";
import {
  parseRecommendation,
  estimateProcurementWindow,
  matchMaterials,
  specsFromRow,
} from "@/lib/material_matcher";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DimensionScore {
  score: number;
  reasoning: string;
}

export interface ScoreResult {
  totalScore: number;
  grade: "A" | "B" | "C" | "D";
  dimensions: {
    procurement: DimensionScore;
    factoryMatch: DimensionScore;
    reachability: DimensionScore;
    value: DimensionScore;
    confidence: DimensionScore;
  };
  summary: string;
  recommendedAction: string;
}

// ---------------------------------------------------------------------------
// EPC contractor detection (mirrors export_opportunities.ts)
// ---------------------------------------------------------------------------

const EPC_KEYWORDS = [
  "SBM Offshore", "MODEC", "TechnipFMC", "Saipem", "BW Offshore",
  "Yinson", "Bumi Armada", "Teekay", "Altera", "Bluewater",
  "COSCO", "Sembcorp", "Keppel", "Hyundai Heavy", "Samsung Heavy",
  "Daewoo", "DSME", "McDermott", "Subsea 7", "Wood Group",
  "Worley", "Aker Solutions", "Petrofac", "Fluor",
];

function hasEpcContractor(procurementChain?: string): boolean {
  if (!procurementChain) return false;
  const lower = procurementChain.toLowerCase();
  return EPC_KEYWORDS.some((kw) => lower.includes(kw.toLowerCase()));
}

// ---------------------------------------------------------------------------
// Phase keyword detection for procurement window inference
// ---------------------------------------------------------------------------

const FEED_FID_KEYWORDS = ["FEED", "FID", "front-end engineering", "final investment decision"];
const EARLY_STAGE_KEYWORDS = ["concept", "pre-feasibility", "feasibility", "pre-FEED", "pre-FID"];

function hasFeedOrFid(text?: string): boolean {
  if (!text) return false;
  const upper = text.toUpperCase();
  return FEED_FID_KEYWORDS.some((kw) => upper.includes(kw.toUpperCase()));
}

// ---------------------------------------------------------------------------
// Scoring helpers
// ---------------------------------------------------------------------------

function clampInRange(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value) || value < min) return fallback;
  if (value > max) return max;
  return value;
}

/** Convert 0-20 sub-score to a 0-20 integer in the given bracket. */
function scoreInBracket(
  bracket: { min: number; max: number },
  factor: number, // 0-1 where 1 = best in bracket
): number {
  const span = bracket.max - bracket.min;
  return Math.round(bracket.min + span * Math.min(1, Math.max(0, factor)));
}

// ---------------------------------------------------------------------------
// Dimension 1: Procurement Probability (0-20)
// ---------------------------------------------------------------------------

function scoreProcurement(
  project: Project,
  procWindow: ReturnType<typeof estimateProcurementWindow>,
): DimensionScore {
  const { status, procurementChain } = project;
  const statusLower = (status ?? "").toLowerCase();

  // Delivered projects: no procurement opportunity
  if (statusLower === "delivered") {
    return { score: 0, reasoning: "项目已投产交付，无采购机会" };
  }

  if (statusLower === "under construction") {
    // Check fuzzy procurement window from estimateProcurementWindow
    const windowStr = procWindow.window;
    if (windowStr && windowStr !== "时间未定") {
      // "N-M 个月" range → first number is the optimistic start of the window
      const match = windowStr.match(/(\d+)\s*-\s*(\d+)\s*个月/);
      if (match) {
        const monthsAhead = parseInt(match[1], 10);

        if (monthsAhead <= 6) {
          const factor = Math.max(0, 1 - monthsAhead / 6); // closer = higher
          const score = scoreInBracket({ min: 18, max: 20 }, factor);
          return {
            score,
            reasoning: `在建项目，预计采购时间窗为 ${windowStr}，紧迫度高`,
          };
        }
        if (monthsAhead <= 12) {
          const factor = Math.max(0, 1 - (monthsAhead - 6) / 6);
          const score = scoreInBracket({ min: 14, max: 17 }, factor);
          return {
            score,
            reasoning: `在建项目，预计采购时间窗为 ${windowStr}，有一定准备时间`,
          };
        }
        // > 12 months out on Under Construction is unusual but possible
        const score = scoreInBracket({ min: 10, max: 13 }, 0.3);
        return {
          score,
          reasoning: `在建项目，预计采购时间窗较远（${windowStr}），建议持续监控`,
        };
      }

      // Non-month range (e.g. "2026 Q3-Q4") → fall back to confidence brackets
      const factor = procWindow.confidence === "high" ? 1 : 0.4;
      const score = scoreInBracket({ min: 14, max: 20 }, factor);
      return {
        score,
        reasoning: `在建项目，预计采购时间窗为 ${windowStr}，紧迫度较高`,
      };
    }
    // Under Construction but no clear window: default mid-high
    return {
      score: 15,
      reasoning: "在建项目，采购时间窗未明确推断，按中等紧迫度赋分",
    };
  }

  if (statusLower === "planned") {
    const chain = (procurementChain ?? "").toUpperCase();
    const isFeedFid = FEED_FID_KEYWORDS.some((kw) => chain.includes(kw.toUpperCase()));
    const isEarly = EARLY_STAGE_KEYWORDS.some((kw) => chain.includes(kw.toUpperCase()));

    if (isFeedFid) {
      return {
        score: scoreInBracket({ min: 10, max: 13 }, 0.7),
        reasoning: "规划中项目，处于FEED/FID阶段，采购临近",
      };
    }
    if (isEarly) {
      return {
        score: scoreInBracket({ min: 5, max: 9 }, 0.4),
        reasoning: "规划中项目，处于早期概念/可研阶段，采购较远",
      };
    }
    // Planned but no phase info
    return {
      score: scoreInBracket({ min: 5, max: 9 }, 0.6),
      reasoning: "规划中项目，阶段信息不明确",
    };
  }

  // Unknown status: conservative default
  return {
    score: 5,
    reasoning: `项目状态未知（${status || "无数据"}），按最低紧迫度赋分`,
  };
}

// ---------------------------------------------------------------------------
// Dimension 2: Factory Match (0-20)
// ---------------------------------------------------------------------------

function scoreFactoryMatch(project: Project): DimensionScore {
  const rec = parseRecommendation(project.recommendationJson);

  if (rec) {
    const producibleCount = rec.grades.filter((g) => g.in_factory_scope).length;
    if (producibleCount >= 3) {
      return {
        score: scoreInBracket({ min: 18, max: 20 }, Math.min(1, (producibleCount - 3) / 3)),
        reasoning: `${producibleCount} 种推荐材质在工厂生产能力范围内，匹配度优秀`,
      };
    }
    if (producibleCount >= 1) {
      const factor = (producibleCount - 1) / 2; // 1→0, 2→0.5
      return {
        score: scoreInBracket({ min: 12, max: 17 }, factor),
        reasoning: `${producibleCount} 种推荐材质可生产，部分匹配`,
      };
    }
    return {
      score: scoreInBracket({ min: 0, max: 3 }, 0),
      reasoning: "推荐材质均不在工厂生产能力范围内",
    };
  }

  // No recommendationJson: run matchMaterials fresh
  try {
    const specs = specsFromRow({
      water_depth_m: project.waterDepthM,
      oil_capacity_bpd: project.oilCapacityBpd,
      gas_capacity_mmcmd: project.gasCapacityMmcmd,
      hull_type: project.hullType,
      field_name: project.fieldName,
      operator_name: project.operatorName,
      basin: project.basin,
    });
    const freshRec = matchMaterials(specs);
    const producibleCount = freshRec.grades.filter((g) => g.in_factory_scope).length;
    if (producibleCount >= 3) {
      return {
        score: scoreInBracket({ min: 18, max: 20 }, Math.min(1, (producibleCount - 3) / 3)),
        reasoning: `${producibleCount} 种推荐材质在工厂生产能力范围内（实时匹配），匹配度优秀`,
      };
    }
    if (producibleCount >= 1) {
      const factor = (producibleCount - 1) / 2;
      return {
        score: scoreInBracket({ min: 12, max: 17 }, factor),
        reasoning: `${producibleCount} 种推荐材质可生产（实时匹配），部分匹配`,
      };
    }
    return {
      score: scoreInBracket({ min: 0, max: 3 }, 0),
      reasoning: "推荐材质均不在工厂生产能力范围内（实时匹配）",
    };
  } catch {
    return {
      score: 5,
      reasoning: "无推荐材质数据，无法评估工厂匹配度",
    };
  }
}

// ---------------------------------------------------------------------------
// Dimension 3: Reachability (0-20)
// ---------------------------------------------------------------------------

function scoreReachability(project: Project): DimensionScore {
  const { procurementChain, operatorName } = project;

  const hasEpc = hasEpcContractor(procurementChain);
  const hasOperator = !!operatorName && operatorName.trim().length > 0;
  const hasProcurementChain = !!procurementChain && procurementChain.trim().length > 0;

  if (hasEpc) {
    // Extract EPC name for reasoning
    const entities = (procurementChain ?? "").split(/,\s*/);
    const epcNames = entities.filter((e) =>
      EPC_KEYWORDS.some((kw) => e.toLowerCase().includes(kw.toLowerCase())),
    );
    const epcList = epcNames.length > 0 ? epcNames.join(", ") : "已知EPC承包商";
    return {
      score: scoreInBracket({ min: 15, max: 20 }, 0.8),
      reasoning: `已识别EPC承包商：${epcList}，采购链清晰，可触达性高`,
    };
  }

  if (hasOperator || hasProcurementChain) {
    const detail = hasOperator
      ? `已知业主/运营商：${operatorName}`
      : "有采购链信息但未识别EPC承包商";
    return {
      score: scoreInBracket({ min: 8, max: 14 }, hasOperator ? 0.7 : 0.4),
      reasoning: `${detail}，需进一步确认采购控制方`,
    };
  }

  return {
    score: scoreInBracket({ min: 0, max: 7 }, 0.2),
    reasoning: "无采购链实体信息，可触达性低",
  };
}

// ---------------------------------------------------------------------------
// Dimension 4: Project Value (0-20)
// ---------------------------------------------------------------------------

function scoreValue(project: Project): DimensionScore {
  const oil = project.oilCapacityBpd;
  const gas = project.gasCapacityMmcmd;

  // Large project: oil > 150k bpd or gas > 10k MMcmd
  if (oil != null && oil > 150000) {
    const factor = Math.min(1, (oil - 150000) / 150000); // up to 300k → factor 1
    return {
      score: scoreInBracket({ min: 16, max: 20 }, factor),
      reasoning: `大型项目，原油产能 ${oil.toLocaleString()} bpd，材料需求量大`,
    };
  }
  if (gas != null && gas > 10000) {
    const factor = Math.min(1, (gas - 10000) / 10000);
    return {
      score: scoreInBracket({ min: 16, max: 20 }, factor),
      reasoning: `大型项目，天然气产能 ${gas.toLocaleString()} MMcmd，材料需求量大`,
    };
  }

  // Medium project: oil 80k-150k bpd
  if (oil != null && oil >= 80000) {
    const factor = (oil - 80000) / 70000; // 80k→0, 150k→1
    return {
      score: scoreInBracket({ min: 10, max: 15 }, factor),
      reasoning: `中型项目，原油产能 ${oil.toLocaleString()} bpd`,
    };
  }

  // Small or unknown
  if (oil != null && oil > 0) {
    const factor = oil / 80000; // 0→0, 80k→1
    return {
      score: scoreInBracket({ min: 0, max: 9 }, factor),
      reasoning: `原油产能 ${oil.toLocaleString()} bpd，规模较小`,
    };
  }
  if (gas != null && gas > 0) {
    const factor = Math.min(1, gas / 10000);
    return {
      score: scoreInBracket({ min: 0, max: 9 }, factor),
      reasoning: `天然气产能 ${gas.toLocaleString()} MMcmd，规模一般`,
    };
  }

  // No capacity data
  return {
    score: 5,
    reasoning: "无产能数据，按中等偏低规模评估",
  };
}

// ---------------------------------------------------------------------------
// Dimension 5: Information Confidence (0-20)
// ---------------------------------------------------------------------------

function scoreConfidence(project: Project): DimensionScore {
  const conf = (project.confidence ?? "").toLowerCase();

  if (conf === "high") {
    return {
      score: scoreInBracket({ min: 18, max: 20 }, 0.8),
      reasoning: "信息来源可信度高（官方/一手来源），决策依据充分",
    };
  }

  if (conf === "medium") {
    return {
      score: scoreInBracket({ min: 10, max: 17 }, 0.6),
      reasoning: "信息来源可信度中等，建议结合其他渠道交叉验证",
    };
  }

  if (conf === "low") {
    return {
      score: scoreInBracket({ min: 0, max: 9 }, 0.3),
      reasoning: "信息来源可信度低，需要进一步确认",
    };
  }

  // Missing confidence
  return {
    score: 5,
    reasoning: "无可信度评估数据",
  };
}

// ---------------------------------------------------------------------------
// Summary & recommended action
// ---------------------------------------------------------------------------

function generateSummary(
  total: number,
  grade: string,
  dims: Record<string, DimensionScore>,
): string {
  if (grade === "A") {
    return `高分商机（${total}分）：采购紧迫、工厂匹配度高、可触达性强，建议优先跟进`;
  }
  if (grade === "B") {
    return `良好商机（${total}分）：具备跟进价值，部分维度有提升空间`;
  }
  if (grade === "C") {
    return `一般商机（${total}分）：信息缺口较多，建议补充情报后重新评估`;
  }
  return `低分项目（${total}分）：当前不适合投入销售资源，等待条件变化`;
}

function actionForGrade(grade: string): string {
  switch (grade) {
    case "A":
      return "立即联系EPC承包商与业主，争取进入询价清单";
    case "B":
      return "监控项目进展，准备技术方案与客户案例";
    case "C":
      return "持续关注项目动态，补充信息缺口";
    default:
      return "低优先级，等待更多信息或项目阶段变化";
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Score a project's sales opportunity across 5 dimensions.
 *
 * @param project - The project to score (from the database or candidate events).
 * @returns A ScoreResult with total, grade, dimension details, summary, and action.
 */
export function scoreOpportunity(project: Project): ScoreResult {
  // Compute procurement window once (used in scoring)
  const procWindow = estimateProcurementWindow(project);

  const procurement = scoreProcurement(project, procWindow);
  const factoryMatch = scoreFactoryMatch(project);
  const reachability = scoreReachability(project);
  const value = scoreValue(project);
  const confidence = scoreConfidence(project);

  const totalScore = procurement.score + factoryMatch.score + reachability.score + value.score + confidence.score;
  const grade = scoreToGrade(totalScore);
  const summary = generateSummary(totalScore, grade, {
    procurement,
    factoryMatch,
    reachability,
    value,
    confidence,
  });
  const recommendedAction = actionForGrade(grade);

  return {
    totalScore,
    grade,
    dimensions: {
      procurement,
      factoryMatch,
      reachability,
      value,
      confidence,
    },
    summary,
    recommendedAction,
  };
}

/**
 * Map a numeric score (0-100) to a letter grade.
 */
export function scoreToGrade(score: number): "A" | "B" | "C" | "D" {
  if (score >= 80) return "A";
  if (score >= 60) return "B";
  if (score >= 40) return "C";
  return "D";
}

/**
 * Return Tailwind CSS classes for a score grade badge.
 * A = green (excellent opportunity), B = blue (good), C = orange (marginal), D = gray (low).
 */
export function scoreBadgeClass(grade: string): string {
  switch (grade) {
    case "A":
      return "bg-fpso-green/15 text-fpso-green";
    case "B":
      return "bg-fpso-blue/15 text-fpso-blue";
    case "C":
      return "bg-fpso-orange/15 text-fpso-orange";
    case "D":
    default:
      return "bg-fpso-muted/15 text-fpso-muted";
  }
}

/**
 * Return a Tailwind CSS color for the progress bar fill based on grade.
 */
export function scoreProgressColor(grade: string): string {
  switch (grade) {
    case "A":
      return "bg-fpso-green";
    case "B":
      return "bg-fpso-blue";
    case "C":
      return "bg-fpso-orange";
    case "D":
    default:
      return "bg-fpso-muted";
  }
}
