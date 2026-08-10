/**
 * Rule Optimizer (S7 — Follow-up Loop)
 * ====================================
 *
 * Collects sales corrections data from follow_ups, analyzes correction patterns,
 * and generates optimization suggestions for the material_matcher rules.
 *
 * Read-only analysis only. No automatic rule modification.
 * Output is a JSON report for human review before any rule update.
 *
 * Analysis dimensions:
 *   1. Material grade correction ratio — how often do salespeople override
 *      the system-recommended grade? Which grades are most commonly corrected?
 *   2. Procurement timeline accuracy — how often do actual dates differ from
 *      estimated windows?
 *   3. Status distribution — breakdown of follow-up outcomes per project.
 */

import type { FollowUp, FollowUpCorrections } from "@/hooks/useFollowUp";
import { matchMaterials, specsFromRow } from "@/lib/material_matcher";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MaterialCorrectionStats {
  /** System-recommended grade that was corrected. */
  systemGrade: string;
  /** What the salesperson reported as actual. */
  actualGrade: string;
  /** How many times this correction pair occurred. */
  count: number;
  /** Percentage of total corrections this pair represents. */
  percentage: number;
}

export interface ProcurementCorrectionStats {
  /** How many procurement timeline corrections were made. */
  totalCorrections: number;
  /** Average delta in months (actual - estimated). Positive = later than estimated. */
  avgDeltaMonths: number;
  /** Individual correction deltas for detailed review. */
  deltas: { projectId: string; estimatedDate: string; actualDate: string; deltaMonths: number }[];
}

export interface OptimizationReport {
  generatedAt: string;
  totalFollowUps: number;
  followUpsWithCorrections: number;
  /** Distribution of follow-up statuses. */
  statusDistribution: Record<string, number>;
  /** Material grade corrections grouped by (system → actual) pairs. */
  materialCorrections: MaterialCorrectionStats[];
  /** Procurement timeline accuracy analysis. */
  procurementCorrections: ProcurementCorrectionStats;
  /** Top suggested rule adjustments (for human review). */
  suggestions: OptimizationSuggestion[];
}

export interface OptimizationSuggestion {
  /** Which rule or area the suggestion targets. */
  target: string;
  /** What the data shows. */
  finding: string;
  /** Recommended action. */
  recommendation: string;
  /** Confidence in this suggestion based on sample size. */
  confidence: "high" | "medium" | "low";
}

// ---------------------------------------------------------------------------
// Analysis functions
// ---------------------------------------------------------------------------

/**
 * Analyze material grade corrections from follow-up records.
 *
 * Groups corrections by (system grade → actual grade) pairs and calculates
 * frequencies. Only includes records where actualMaterial is set.
 */
export function analyzeMaterialCorrections(
  followUps: FollowUp[],
): MaterialCorrectionStats[] {
  const pairCounts = new Map<string, { systemGrade: string; actualGrade: string; count: number }>();

  for (const fu of followUps) {
    const c = fu.corrections as FollowUpCorrections | null;
    if (!c?.actualMaterial) continue;

    // Infer system grade from project context — we don't have it directly
    // in follow_ups, so use the actualMaterial as the key insight:
    // "system recommended X, but actual is Y"
    // For now, we pair "system_inferred" with the actual grade
    const key = `system_inferred → ${c.actualMaterial}`;
    const existing = pairCounts.get(key);
    if (existing) {
      existing.count++;
    } else {
      pairCounts.set(key, {
        systemGrade: "system_inferred",
        actualGrade: c.actualMaterial,
        count: 1,
      });
    }
  }

  const totalWithCorrections = followUps.filter(
    (fu) => !!(fu.corrections as FollowUpCorrections | null)?.actualMaterial,
  ).length;

  return Array.from(pairCounts.values())
    .map((entry) => ({
      ...entry,
      percentage: totalWithCorrections > 0
        ? Math.round((entry.count / totalWithCorrections) * 100)
        : 0,
    }))
    .sort((a, b) => b.count - a.count);
}

/**
 * Analyze procurement timeline corrections.
 *
 * Compares actual procurement dates (from corrections) against system estimates.
 */
export function analyzeProcurementCorrections(
  followUps: FollowUp[],
): ProcurementCorrectionStats {
  const deltas: ProcurementCorrectionStats["deltas"] = [];

  for (const fu of followUps) {
    const c = fu.corrections as FollowUpCorrections | null;
    if (!c?.actualProcurementDate) continue;

    // We can't recover the original estimated date from follow_ups alone,
    // so we log the actual date for manual comparison.
    deltas.push({
      projectId: fu.project_id,
      estimatedDate: "unknown (see project timeline)",
      actualDate: c.actualProcurementDate,
      deltaMonths: 0, // requires joining with project data
    });
  }

  const totalCorrections = deltas.length;
  const avgDeltaMonths = totalCorrections > 0
    ? Math.round(deltas.reduce((sum, d) => sum + d.deltaMonths, 0) / totalCorrections)
    : 0;

  return {
    totalCorrections,
    avgDeltaMonths,
    deltas,
  };
}

/**
 * Build status distribution counts from follow-up records.
 */
export function buildStatusDistribution(
  followUps: FollowUp[],
): Record<string, number> {
  const dist: Record<string, number> = {
    contacted: 0,
    valid: 0,
    inquiry: 0,
    invalid: 0,
    closed: 0,
  };

  for (const fu of followUps) {
    if (dist[fu.status] !== undefined) {
      dist[fu.status]++;
    }
  }

  return dist;
}

/**
 * Generate optimization suggestions based on correction patterns.
 *
 * Rules of thumb:
 *   - If a grade appears in >20% of corrections, suggest reviewing that rule.
 *   - If procurement timeline corrections are frequent, suggest recalibration.
 *   - If "invalid" rate is high, suggest adjusting factory-match thresholds.
 */
export function generateSuggestions(
  materialStats: MaterialCorrectionStats[],
  procurementStats: ProcurementCorrectionStats,
  statusDist: Record<string, number>,
  totalFollowUps: number,
): OptimizationSuggestion[] {
  const suggestions: OptimizationSuggestion[] = [];

  // Material grade corrections
  for (const stat of materialStats) {
    if (stat.percentage >= 20) {
      suggestions.push({
        target: `material_matcher grade recommendation: ${stat.actualGrade}`,
        finding: `${stat.percentage}% of corrections (${stat.count} records) indicate system recommended a different grade but actual material is ${stat.actualGrade}.`,
        recommendation: `Review rules in material_matcher.ts that select grades for projects matching this profile. Consider adding or strengthening the rule that recommends ${stat.actualGrade}.`,
        confidence: stat.count >= 5 ? "high" : stat.count >= 3 ? "medium" : "low",
      });
    }
  }

  // Procurement timeline accuracy
  if (procurementStats.totalCorrections > 0) {
    const ratio = totalFollowUps > 0
      ? Math.round((procurementStats.totalCorrections / totalFollowUps) * 100)
      : 0;
    if (ratio >= 15) {
      suggestions.push({
        target: "estimateProcurementWindow timing heuristics",
        finding: `${ratio}% of follow-ups (${procurementStats.totalCorrections} records) include procurement timeline corrections. Sales team reports actual dates differ from system estimates.`,
        recommendation: "Review estimateProcurementWindow() phase-to-months offsets. Consider shortening or lengthening default windows based on sales feedback.",
        confidence: procurementStats.totalCorrections >= 5 ? "high" : "medium",
      });
    }
  }

  // Status distribution insights
  const invalidRate = totalFollowUps > 0
    ? Math.round(((statusDist.invalid ?? 0) / totalFollowUps) * 100)
    : 0;

  if (invalidRate >= 30) {
    suggestions.push({
      target: "opportunity_scorer factory match threshold",
      finding: `${invalidRate}% of followed-up projects marked as 'invalid'. High false-positive rate may indicate scoring thresholds are too lenient.`,
      recommendation: "Consider raising the minimum factory-match score threshold or adding additional qualification criteria before recommending pursuit.",
      confidence: totalFollowUps >= 10 ? "high" : "medium",
    });
  }

  const closedRate = totalFollowUps > 0
    ? Math.round(((statusDist.closed ?? 0) / totalFollowUps) * 100)
    : 0;

  if (closedRate >= 20) {
    suggestions.push({
      target: "opportunity_scorer grade thresholds",
      finding: `${closedRate}% of followed-up projects resulted in closed deals. Positive signal for current scoring model.`,
      recommendation: "Document common characteristics of closed projects to refine scoring weights. Current model appears directionally correct.",
      confidence: totalFollowUps >= 10 ? "high" : "medium",
    });
  }

  return suggestions;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Run the full optimization analysis on a set of follow-up records.
 *
 * Produces a comprehensive report suitable for human review. Does NOT modify
 * any rules or database state.
 *
 * @param followUps - All follow-up records (typically across all users).
 * @returns An OptimizationReport with stats and actionable suggestions.
 */
export function runOptimization(followUps: FollowUp[]): OptimizationReport {
  const followUpsWithCorrections = followUps.filter(
    (fu) => {
      const c = fu.corrections as FollowUpCorrections | null;
      return c && (c.actualMaterial || c.actualProcurementDate);
    },
  ).length;

  const statusDist = buildStatusDistribution(followUps);
  const materialStats = analyzeMaterialCorrections(followUps);
  const procurementStats = analyzeProcurementCorrections(followUps);
  const suggestions = generateSuggestions(
    materialStats,
    procurementStats,
    statusDist,
    followUps.length,
  );

  return {
    generatedAt: new Date().toISOString(),
    totalFollowUps: followUps.length,
    followUpsWithCorrections,
    statusDistribution: statusDist,
    materialCorrections: materialStats,
    procurementCorrections: procurementStats,
    suggestions,
  };
}

/**
 * Convenience: fetch all corrections from Supabase and run optimization.
 *
 * Usage:
 *   import { supabase } from "@/db/supabase";
 *   import { fetchAndOptimize } from "@/lib/rule_optimizer";
 *   const report = await fetchAndOptimize(supabase);
 */
export async function fetchAndOptimize(
  supabaseClient: { from: (table: string) => { select: (columns: string) => Promise<{ data: unknown; error: unknown }> } },
): Promise<OptimizationReport | null> {
  try {
    const { data, error } = await supabaseClient.from("follow_ups").select("*");
    if (error) {
      console.error("Failed to fetch follow-ups for optimization:", error);
      return null;
    }
    const followUps = (data as FollowUp[]) ?? [];
    return runOptimization(followUps);
  } catch (err) {
    console.error("fetchAndOptimize error:", err);
    return null;
  }
}
