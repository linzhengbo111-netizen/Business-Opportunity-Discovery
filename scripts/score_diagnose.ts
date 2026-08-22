/**
 * Diagnostic: score distribution across all projects (Battle Cards view).
 * Usage: npx -y tsx scripts/score_diagnose.ts
 */
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import { filterMatureProjects, maturityFor } from "@/lib/project_maturity";
import { phaseFromRow } from "@/lib/project_phase";
import { parseCorrosiveMedia } from "@/lib/material_matcher";
import { COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import type { Project } from "@/data/projects";

const SUPABASE_URL = "https://zbxogsfnhagcavbvhypk.supabase.co";
const KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y";

function normalizeCountry(raw: string): string {
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  for (const [alias, canonical] of Object.entries(COUNTRY_ALIASES)) {
    if (lower === alias.toLowerCase()) return canonical;
  }
  return trimmed;
}

function toNum(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function toStr(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s.length > 0 ? s : null;
}

function mapRowToProject(row: Record<string, unknown>): Project {
  const rawName = String(row.name ?? "");
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
  return {
    name,
    country: normalizeCountry(String(row.country ?? "")),
    flag: String(row.flag ?? ""),
    phase: phaseFromRow(row),
    summary: String(row.summary ?? ""),
    source: { name: String(row.source_name ?? ""), url: String(row.source_url ?? ""), date: String(row.source_date ?? "") },
    stainlessSteel: String(row.stainless_steel ?? ""),
    application: String(row.application ?? ""),
    industry: String(row.industry ?? "FPSO"),
    confidence: String(row.confidence ?? "medium") as "high" | "medium" | "low",
    procurementChain: String(row.procurement_chain ?? ""),
    waterDepthM: toNum(row.water_depth_m),
    oilCapacityBpd: toNum(row.oil_capacity_bpd),
    gasCapacityMmcmd: toNum(row.gas_capacity_mmcmd),
    hullType: toStr(row.hull_type),
    fieldName: toStr(row.field_name),
    operatorName: toStr(row.operator_name),
    basin: toStr(row.basin),
    recommendationJson: toStr(row.recommendation_json),
    createdAt: toStr(row.created_at),
    corrosiveMedia: parseCorrosiveMedia(row.corrosive_media),
  };
}

async function fetchAllRows(
  table: string,
  orderBy = "name.asc",
): Promise<Record<string, unknown>[]> {
  const rows: Record<string, unknown>[] = [];
  let offset = 0;
  while (true) {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/${table}?select=*&order=${orderBy}&offset=${offset}&limit=1000`,
      { headers: { apikey: KEY, Authorization: `Bearer ${KEY}` } },
    );
    const data = (await res.json()) as Record<string, unknown>[];
    if (!Array.isArray(data) || data.length === 0) break;
    rows.push(...data);
    offset += data.length;
    if (data.length < 1000) break;
  }
  return rows;
}

async function main() {
  const [projectRows, eventRows] = await Promise.all([
    fetchAllRows("projects"),
    fetchAllRows("candidate_events", "id.asc"),
  ]);
  console.log(`projects: ${projectRows.length} rows, candidate_events: ${eventRows.length} rows`);

  // Event counts per canonical id (all events, not only accepted — mirrors useTimelineEventCounts)
  const eventCounts = new Map<string, number>();
  for (const row of eventRows) {
    const pid = String(row.canonical_project_id ?? "").trim();
    if (!pid) continue;
    eventCounts.set(pid, (eventCounts.get(pid) ?? 0) + 1);
  }

  const projects = projectRows.map(mapRowToProject);
  const mature = filterMatureProjects(projects, eventCounts, false);
  console.log(`mature (tech params + events): ${mature.length} / ${projects.length}`);

  const dist: Record<string, number> = { A: 0, B: 0, C: 0, D: 0 };
  const rows: { name: string; phase: string; confidence: string; score: number; grade: string; mature: boolean }[] = [];

  for (const p of projects) {
    const r = scoreOpportunity(p);
    dist[r.grade]++;
    rows.push({
      name: p.name,
      phase: p.phase ?? "Unknown",
      confidence: p.confidence ?? "?",
      score: r.totalScore,
      grade: r.grade,
      mature: maturityFor(p, eventCounts) === "mature",
    });
  }

  console.log("\n== score distribution (ALL projects):", dist);

  const inBattle = rows.filter((r) => r.mature && (r.grade === "A" || r.grade === "B"));
  console.log(`\n== Battle Cards current view (mature + A/B): ${inBattle.length}`);
  for (const r of inBattle) console.log(`   ${r.grade} ${r.score}  ${r.name}  [${r.phase}] ${r.confidence}`);

  const matureC = rows.filter((r) => r.mature && r.grade === "C").sort((a, b) => b.score - a.score);
  console.log(`\n== mature but C grade (top 15): ${matureC.length}`);
  for (const r of matureC.slice(0, 15)) console.log(`   ${r.score}  ${r.name}  [${r.phase}] ${r.confidence}`);

  const notMatureHigh = rows
    .filter((r) => !r.mature && (r.grade === "A" || r.grade === "B"))
    .sort((a, b) => b.score - a.score);
  console.log(`\n== non-mature but A/B grade (top 15): ${notMatureHigh.length}`);
  for (const r of notMatureHigh.slice(0, 15)) console.log(`   ${r.score}  ${r.name}  [${r.phase}] ${r.confidence}`);

  console.log("\n== pinned three:");
  for (const r of rows.filter((r) =>
    /ALMIRANTE|BACALHAU|SEPETIBA/i.test(r.name),
  )) console.log(`   ${r.grade} ${r.score}  ${r.name}  [${r.phase}] ${r.confidence} mature=${r.mature}`);

  // Accepted-only event counts per canonical id
  const acceptedCounts = new Map<string, number>();
  for (const row of eventRows) {
    if (String(row.review_status ?? "").toLowerCase() !== "accepted") continue;
    const pid = String(row.canonical_project_id ?? "").trim();
    if (!pid) continue;
    acceptedCounts.set(pid, (acceptedCounts.get(pid) ?? 0) + 1);
  }

  const scoredAll = projects.map((p) => {
    const r = scoreOpportunity(p);
    const canon = normalizeProjectName(p.name);
    return {
      name: p.name,
      phase: p.phase,
      confidence: p.confidence,
      score: r.totalScore,
      grade: r.grade,
      anyEvents: canon ? (eventCounts.get(canon) ?? 0) : 0,
      acceptedEvents: canon ? (acceptedCounts.get(canon) ?? 0) : 0,
      hasPhase: p.phase != null && p.phase !== "Unknown",
      isUk: /UK|United Kingdom/i.test(p.country),
    };
  });

  const byAccepted = scoredAll.filter((r) => r.acceptedEvents > 0);
  const byAnyEvent = scoredAll.filter((r) => r.anyEvents > 0);
  console.log(`\n== projects with >=1 accepted event: ${byAccepted.length}`);
  console.log(`== projects with >=1 any event: ${byAnyEvent.length}`);

  for (const label of ["accepted+phase", "anyevent+phase"]) {
    const pool = label === "accepted+phase" ? byAccepted : byAnyEvent;
    const withPhase = pool.filter((r) => r.hasPhase);
    console.log(`\n== gate ${label}: ${withPhase.length} projects`);
    for (const [lo, hi] of [[80, 100], [60, 79], [55, 59], [50, 54], [45, 49], [0, 44]] as const) {
      const inBucket = withPhase.filter((r) => r.score >= lo && r.score <= hi);
      const uk = inBucket.filter((r) => r.isUk).length;
      console.log(`   score ${lo}-${hi}: ${inBucket.length} (UK: ${uk})`);
    }
    console.log("   top 18 by score:");
    for (const r of [...withPhase].sort((a, b) => b.score - a.score).slice(0, 18)) {
      console.log(`     ${r.score} ${r.grade}  ${r.name}  [${r.phase}] ${r.confidence}${r.isUk ? "  UK" : ""} acc=${r.acceptedEvents}`);
    }
  }
}

main();
