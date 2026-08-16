/**
 * Opportunity List CSV Export Utility
 * ===================================
 *
 * Generates and triggers download of a CSV file containing only projects
 * where at least one recommended stainless steel grade is within the
 * factory's production capability (in_factory_scope = true).
 *
 * Columns: project name, country, phase, estimated procurement window,
 * operator, EPC contractor, recommended producible grades, inferred
 * product types, target customer type, project URL.
 */

import type { Project } from "@/data/projects";
import {
  matchMaterials,
  specsFromRow,
  inferProductNeeds,
  matchCustomerType,
  estimateProcurementWindow,
  parseRecommendation,
} from "@/lib/material_matcher";
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import { generateBattleCard } from "@/lib/battle_card";

/** Check whether a project has at least one factory-producible grade. */
function hasProducibleGrade(project: Project): boolean {
  // Prefer persisted recommendation_json
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    return rec.grades.some((g) => g.in_factory_scope);
  }

  // Fall back to running the engine fresh
  const specs = specsFromRow({
    water_depth_m: project.waterDepthM,
    oil_capacity_bpd: project.oilCapacityBpd,
    gas_capacity_mmcmd: project.gasCapacityMmcmd,
    hull_type: project.hullType,
    field_name: project.fieldName,
    operator_name: project.operatorName,
    basin: project.basin,
  });
  const result = matchMaterials(specs);
  return result.grades.some((g) => g.in_factory_scope);
}

/** Get producible grade names for a project. */
function getProducibleGrades(project: Project): string[] {
  const rec = parseRecommendation(project.recommendationJson);
  if (rec) {
    return rec.grades.filter((g) => g.in_factory_scope).map((g) => g.grade);
  }

  const specs = specsFromRow({
    water_depth_m: project.waterDepthM,
    oil_capacity_bpd: project.oilCapacityBpd,
    gas_capacity_mmcmd: project.gasCapacityMmcmd,
    hull_type: project.hullType,
    field_name: project.fieldName,
    operator_name: project.operatorName,
    basin: project.basin,
  });
  return matchMaterials(specs).grades
    .filter((g) => g.in_factory_scope)
    .map((g) => g.grade);
}

/** Extract EPC contractor name from procurement chain string. */
function extractEpcContractor(procurementChain?: string): string {
  if (!procurementChain) return "";
  const epcKeywords = [
    "SBM Offshore", "MODEC", "TechnipFMC", "Saipem", "BW Offshore",
    "Yinson", "Bumi Armada", "Teekay", "Altera", "Bluewater",
    "COSCO", "Sembcorp", "Keppel", "Hyundai Heavy", "Samsung Heavy",
    "Daewoo", "DSME", "McDermott", "Subsea 7", "Wood Group",
    "Worley", "Aker Solutions", "Petrofac", "Fluor",
  ];
  const entities = procurementChain.split(/,\s*/);
  const epc = entities.filter((e) =>
    epcKeywords.some((kw) => e.toLowerCase().includes(kw.toLowerCase())),
  );
  return epc.join("; ") || entities.slice(0, 2).join("; ");
}

/**
 * Escape a CSV cell value. Wraps in double quotes and escapes internal quotes.
 */
function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

/**
 * Generate and download a CSV file of factory-qualified opportunities.
 *
 * Only projects where at least one recommended grade is producible
 * are included. The file is named MT_Stainless_Steel_Opportunity_List_YYYY-MM-DD.csv
 * and includes a UTF-8 BOM for Excel compatibility with Chinese characters.
 *
 * @param projects - Array of projects (pre-filtered by user's current view).
 * @param baseUrl - Base URL for constructing project detail links.
 */
export function exportOpportunityList(projects: Project[], baseUrl?: string): void {
  // Filter: only projects with at least one producible grade
  const qualified = projects.filter(hasProducibleGrade);

  if (qualified.length === 0) {
    alert("No factory-qualified projects in current view. Try adjusting filters.");
    return;
  }

  const today = new Date().toISOString().slice(0, 10);

  // CSV header (Chinese + English for technical fields)
  const headers = [
    "项目名称",
    "国家",
    "状态",
    "预计采购时间窗",
    "时间窗置信度",
    "业主/运营商",
    "EPC承包商",
    "推荐不锈钢牌号（工厂可做）",
    "推荐产品类型（AI推断）",
    "目标客户类型",
    "推理说明",
    "机会评分",
    "等级",
    "项目来源",
    "为什么值得追",
    "推荐产品",
    "联系谁",
    "何时联系",
    "下一步行动",
  ];

  // Score all qualified projects and sort by score descending
  const scored = qualified.map((project) => ({
    project,
    score: scoreOpportunity(project),
  }));
  scored.sort((a, b) => b.score.totalScore - a.score.totalScore);

  const rows: string[][] = [];

  for (const { project, score: scoreResult } of scored) {
    const producibleGrades = getProducibleGrades(project);

    // Build description text for product inference and customer matching
    const descriptionText = [
      project.name,
      project.summary,
      project.application,
    ].filter(Boolean).join(" ");

    const productNeeds = inferProductNeeds(descriptionText);
    const customerMatch = matchCustomerType(descriptionText);
    const procurementWindow = estimateProcurementWindow(project);

    const productLabels = productNeeds.length > 0
      ? productNeeds.map((p) => `${p.label}(${p.confidence})`).join("; ")
      : "—";

    const customerLabel = customerMatch.matchedLabels.length > 0
      ? customerMatch.matchedLabels.join("; ")
      : customerMatch.hasExclusion
        ? "非目标客户"
        : "—";

    const epcContractor = extractEpcContractor(project.procurementChain);
    const sourceUrl = project.source?.url || "";
    const sourceName = project.source?.name || "";

    // Generate battle card for enriched CSV export
    const battleCard = generateBattleCard(project);
    const contactInfo = battleCard.whoToContact.recommendedRole;

    rows.push([
      project.name,
      project.country,
      project.phase || "Unknown",
      procurementWindow.window,
      procurementWindow.confidence,
      project.operatorName || sourceName || "",
      epcContractor,
      producibleGrades.join("; ") || "316L (default)",
      productLabels,
      customerLabel,
      procurementWindow.reasoning,
      String(scoreResult.totalScore),
      scoreResult.grade,
      sourceUrl || sourceName || "",
      battleCard.whyPursue,
      battleCard.whatToPush.join(", "),
      contactInfo,
      battleCard.whenToContact,
      battleCard.nextAction,
    ]);
  }

  // Build CSV with BOM for Excel UTF-8 compatibility
  const csvLines = [
    headers.map(csvCell).join(","),
    ...rows.map((row) => row.map(csvCell).join(",")),
  ];
  const bom = "﻿";
  const csvContent = bom + csvLines.join("\n");

  // Trigger download
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `MT_Stainless_Steel_Opportunity_List_${today}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
