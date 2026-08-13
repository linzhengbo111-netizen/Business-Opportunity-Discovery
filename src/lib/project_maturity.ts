import type { Project } from "@/data/projects";
import { normalizeProjectName } from "@/data/project_aliases";

/**
 * 商机成熟度分类（纯前端计算，无数据库字段）：
 *
 *   成熟商机 (mature)   = 有技术参数 (water_depth_m 或 oil_capacity_bpd)
 *                       + 有采购链 (procurement_chain)
 *                       + 有时间线事件 (至少 1 条 candidate_events 关联)
 *   潜在项目 (potential) = 不满足上述任一条件的项目
 */

export type ProjectMaturity = "mature" | "potential";

/** Count of candidate_events linked to the project's canonical id. */
export function eventCountFor(
  project: Project,
  eventCounts: Map<string, number>,
): number {
  const canonicalId = normalizeProjectName(project.name);
  if (!canonicalId) return 0;
  return eventCounts.get(canonicalId) ?? 0;
}

/** Whether the project has any timeline data at all. */
export function hasTimelineData(
  project: Project,
  eventCounts: Map<string, number>,
): boolean {
  return eventCountFor(project, eventCounts) >= 1;
}

/** Whether the project qualifies as a mature opportunity. */
export function isMatureProject(
  project: Project,
  eventCounts: Map<string, number>,
): boolean {
  const hasTechParams =
    project.waterDepthM != null || project.oilCapacityBpd != null;
  const hasProcurementChain = (project.procurementChain ?? "").trim().length > 0;
  return hasTechParams && hasProcurementChain && hasTimelineData(project, eventCounts);
}

export function maturityFor(
  project: Project,
  eventCounts: Map<string, number>,
): ProjectMaturity {
  return isMatureProject(project, eventCounts) ? "mature" : "potential";
}

/**
 * Filter a project list to mature opportunities only. Pass `showAll=true`
 * to keep every project (待挖掘 projects get flagged in the UI).
 */
export function filterMatureProjects(
  projects: Project[],
  eventCounts: Map<string, number>,
  showAll: boolean,
): Project[] {
  if (showAll) return projects;
  return projects.filter((p) => isMatureProject(p, eventCounts));
}
