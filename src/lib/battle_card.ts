/**
 * Sales Battle Card Generator (S6)
 * =================================
 *
 * Transforms opportunity scores into actionable sales battle cards.
 * Each card distills project data into a one-page brief: why pursue,
 * what to push, who to contact, when to act, and the next move.
 *
 * Intended for screen, print, and share — no fluff, just what the
 * sales team needs for a first outreach.
 */

import type { Project } from "@/data/projects";
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import {
  parseRecommendation,
  inferProductNeeds,
  estimateProcurementWindow,
} from "@/lib/material_matcher";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BattleCardContact {
  owner?: string;
  operator?: string;
  epcContractor?: string;
  recommendedRole: string;
}

export interface BattleCard {
  projectName: string;
  country: string;
  phase: string;
  totalScore: number;
  grade: "A" | "B" | "C" | "D";
  whyPursue: string;
  whatToPush: string[];
  materialGrades: string[];
  whoToContact: BattleCardContact;
  whenToContact: string;
  nextAction: string;
  evidenceSummary: string;
  projectUrl: string;
  generatedAt: string;
}

// ---------------------------------------------------------------------------
// EPC contractor detection
// ---------------------------------------------------------------------------

const EPC_KEYWORDS = [
  "SBM Offshore", "MODEC", "TechnipFMC", "Saipem", "BW Offshore",
  "Yinson", "Bumi Armada", "Teekay", "Altera", "Bluewater",
  "COSCO", "Sembcorp", "Keppel", "Hyundai Heavy", "Samsung Heavy",
  "Daewoo", "DSME", "McDermott", "Subsea 7", "Wood Group",
  "Worley", "Aker Solutions", "Petrofac", "Fluor",
];

function extractEpcName(procurementChain?: string): string | undefined {
  if (!procurementChain) return undefined;
  const entities = procurementChain.split(/,\s*/);
  const epc = entities.filter((e) =>
    EPC_KEYWORDS.some((kw) => e.toLowerCase().includes(kw.toLowerCase())),
  );
  return epc.length > 0 ? epc.join(", ") : undefined;
}

// ---------------------------------------------------------------------------
// whyPursue — commercial rationale
// ---------------------------------------------------------------------------

function buildWhyPursue(project: Project, scoreResult: ReturnType<typeof scoreOpportunity>): string {
  const parts: string[] = [];

  // Capacity-driven value
  const oil = project.oilCapacityBpd;
  const gas = project.gasCapacityMmcmd;
  if (oil != null && oil >= 80000) {
    parts.push(`原油产能 ${oil.toLocaleString()} bpd，材料需求可观`);
  } else if (gas != null && gas >= 5000) {
    parts.push(`天然气产能 ${gas.toLocaleString()} MMcmd，材料需求可观`);
  }

  // Water depth complexity (deeper = more duplex/super duplex)
  const depth = project.waterDepthM;
  if (depth != null && depth >= 1000) {
    parts.push(`水深 ${depth}m，需要高性能双相不锈钢`);
  } else if (depth != null && depth >= 500) {
    parts.push(`水深 ${depth}m，有双相不锈钢需求`);
  }

  // Corrosive media
  const cm = project.corrosiveMedia as Record<string, unknown> | null | undefined;
  if (cm) {
    const flags: string[] = [];
    if (cm.h2s) flags.push("H₂S");
    if (cm.co2) flags.push("CO₂");
    if (cm.sour_service) flags.push("酸性工况(NACE)");
    if (flags.length > 0) {
      parts.push(`含${flags.join("+")}腐蚀介质，需耐腐蚀合金`);
    }
  }

  // Factory match
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    const producible = rec.grades.filter((g) => g.in_factory_scope);
    if (producible.length >= 3) {
      parts.push(`工厂可生产 ${producible.length} 种推荐牌号，匹配度高`);
    }
  }

  // Procurement urgency
  if (scoreResult.dimensions.procurement.score >= 16) {
    parts.push("采购时间窗紧迫，商机成熟度高");
  } else if (scoreResult.dimensions.procurement.score >= 10) {
    parts.push("采购时间窗明确，适合提前布局");
  }

  // Fallback: use score summary
  if (parts.length === 0) {
    return scoreResult.summary;
  }

  return parts.join("。") + "。";
}

// ---------------------------------------------------------------------------
// whatToPush — recommended products
// ---------------------------------------------------------------------------

function buildWhatToPush(project: Project): string[] {
  const descriptionText = [
    project.name,
    project.summary,
    project.application,
  ].filter(Boolean).join(" ");

  const productNeeds = inferProductNeeds(descriptionText);
  if (productNeeds.length > 0) {
    return productNeeds.map((p) => p.label);
  }

  // Fallback based on material grades
  const rec = parseRecommendation(project.recommendationJson);
  if (rec && rec.applications.length > 0) {
    return rec.applications;
  }

  return ["不锈钢板材/管材（待补充）"];
}

// ---------------------------------------------------------------------------
// materialGrades — producible grades only
// ---------------------------------------------------------------------------

function buildMaterialGrades(project: Project): string[] {
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    return rec.grades
      .filter((g) => g.in_factory_scope)
      .map((g) => g.grade);
  }

  // Check stainlessSteel field for any manual grade data
  if (project.stainlessSteel && project.stainlessSteel.trim()) {
    return [project.stainlessSteel.trim()];
  }

  // No grade data — mark missing instead of leaving the field blank.
  return ["待补充"];
}

// ---------------------------------------------------------------------------
// whoToContact — contact strategy
// ---------------------------------------------------------------------------

function buildWhoToContact(project: Project): BattleCardContact {
  const epcContractor = extractEpcName(project.procurementChain);
  const operator = project.operatorName || undefined;
  const owner = project.source?.name || undefined;

  // Priority: EPC > operator > owner
  let recommendedRole: string;
  if (epcContractor) {
    recommendedRole = `建议首先联系 EPC 承包商：${epcContractor}`;
  } else if (operator) {
    recommendedRole = `建议联系运营商：${operator}`;
  } else if (owner) {
    recommendedRole = `建议联系业主方：${owner}`;
  } else {
    recommendedRole = "采购链信息不足，建议通过行业展会或LinkedIn触达";
  }

  return {
    owner,
    operator,
    epcContractor,
    recommendedRole,
  };
}

// ---------------------------------------------------------------------------
// whenToContact — timing assessment
// ---------------------------------------------------------------------------

function buildWhenToContact(project: Project): string {
  const procWindow = estimateProcurementWindow(project);

  // Fuzzy window ranges only — never specific dates
  if (procWindow.window && procWindow.window !== "时间未定") {
    if (procWindow.confidence === "high") {
      return `采购窗口已开启（${procWindow.window}），建议本周内完成首次触达`;
    }
    if (procWindow.confidence === "medium") {
      return `采购窗口临近（${procWindow.window}），建议本月内建立联系`;
    }
    return `采购窗口预计在 ${procWindow.window}，适合提前布局`;
  }

  // Delivered/completed project: window has passed
  if (procWindow.confidence === "high") {
    return "采购窗口已过（项目已交付），建议转为 MRO 备件商机跟进";
  }

  return "采购时间窗尚未明确，建议通过项目动态持续监控";
}

// ---------------------------------------------------------------------------
// nextAction — concrete next step
// ---------------------------------------------------------------------------

function buildNextAction(project: Project): string {
  const procWindow = estimateProcurementWindow(project);

  // Urgency derived from fuzzy window confidence — no date math
  if (procWindow.confidence === "high" && procWindow.window !== "时间未定") {
    const contact = extractEpcName(project.procurementChain)
      || project.operatorName
      || project.source?.name
      || "项目方";
    return `立即联系${contact}，发送公司资质和产品目录`;
  }
  if (procWindow.confidence === "medium") {
    return "准备技术方案和报价模板，针对性跟进";
  }

  // Default by phase
  const phase = project.phase;
  if (phase === "Procurement") {
    return "立即联系EPC承包商，进入询价清单";
  }
  if (phase === "EPC Award" || phase === "Construction") {
    return "确认采购进度和询价时间节点";
  }
  if (phase === "Approval") {
    return "跟踪FID与EPC授标公告，提前递交资质";
  }
  if (phase === "Planning" || phase === "Design" || phase === "Concept") {
    return "建立初步联系，了解项目规划时间表";
  }

  return "定期关注项目动态，等待合适时机介入";
}

// ---------------------------------------------------------------------------
// evidenceSummary — source attribution
// ---------------------------------------------------------------------------

function buildEvidenceSummary(project: Project): string {
  const parts: string[] = [];
  if (project.source?.name) {
    parts.push(project.source.name);
  }
  if (project.source?.url) {
    parts.push(project.source.url);
  }
  if (project.confidence) {
    const label =
      project.confidence === "high" ? "高可信度" :
      project.confidence === "medium" ? "中可信度" :
      "低可信度";
    parts.push(label);
  }
  return parts.length > 0 ? parts.join(" · ") : "来源待补充";
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate a sales battle card for a project.
 *
 * @param project  - The project to build a battle card for.
 * @param baseUrl  - Base URL for constructing the project detail link.
 * @returns A BattleCard object ready for rendering.
 */
export function generateBattleCard(project: Project, baseUrl?: string): BattleCard {
  const scoreResult = scoreOpportunity(project);

  const whyPursue = buildWhyPursue(project, scoreResult);
  const whatToPush = buildWhatToPush(project);
  const materialGrades = buildMaterialGrades(project);
  const whoToContact = buildWhoToContact(project);
  const whenToContact = buildWhenToContact(project);
  const nextAction = buildNextAction(project);
  const evidenceSummary = buildEvidenceSummary(project);

  // Build project URL
  const origin = baseUrl || (typeof window !== "undefined" ? window.location.origin : "");
  const projectUrl = `${origin}/database?project=${encodeURIComponent(project.name)}`;

  return {
    projectName: project.name,
    country: project.country,
    phase: project.phase || "Unknown",
    totalScore: scoreResult.totalScore,
    grade: scoreResult.grade,
    whyPursue,
    whatToPush,
    materialGrades,
    whoToContact,
    whenToContact,
    nextAction,
    evidenceSummary,
    projectUrl,
    generatedAt: new Date().toISOString(),
  };
}
