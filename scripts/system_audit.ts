/**
 * System audit (2026-08-23) — replicates the three pages' exact filter/sort
 * pipelines against live Supabase and prints distributions.
 * Usage: npx -y tsx scripts/system_audit.ts
 */
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import { hasTimelineData } from "@/lib/project_maturity";
import { phaseFromRow, PHASE_UNKNOWN } from "@/lib/project_phase";
import { parseCorrosiveMedia } from "@/lib/material_matcher";
import { COUNTRY_ALIASES } from "@/data/projects";
import {
  normalizeProjectName,
  getDisplayName,
  priorityProjectRankByName,
  sortPriorityFirst,
} from "@/data/project_aliases";
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

async function fetchAllRows(table: string, orderBy = "name.asc"): Promise<Record<string, unknown>[]> {
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

const PINNED_RE = /ALMIRANTE TAMANDARE|BACALHAU|SEPETIBA/i;
const NOISE_NAMES = ["ABIGAIL", "AFFLECK", "WREN", "YARE", "YORK", "YTHAN"];

async function main() {
  const [projectRows, eventRows] = await Promise.all([
    fetchAllRows("projects"),
    fetchAllRows("candidate_events", "id.asc"),
  ]);
  console.log(`projects: ${projectRows.length}, candidate_events: ${eventRows.length}`);

  // ---- event counts: ALL events (Dashboard/BattleCards gates) vs accepted-only (Timeline) ----
  const allEventCounts = new Map<string, number>();
  const acceptedEventCounts = new Map<string, number>();
  const statusDist: Record<string, number> = {};
  for (const row of eventRows) {
    const status = String(row.review_status ?? "(null)").toLowerCase();
    statusDist[status] = (statusDist[status] ?? 0) + 1;
    const pid = String(row.canonical_project_id ?? "").trim();
    if (!pid) continue;
    allEventCounts.set(pid, (allEventCounts.get(pid) ?? 0) + 1);
    if (status === "accepted") acceptedEventCounts.set(pid, (acceptedEventCounts.get(pid) ?? 0) + 1);
  }
  console.log("\n== candidate_events review_status distribution:", statusDist);
  const noPid = eventRows.filter((r) => !String(r.canonical_project_id ?? "").trim()).length;
  console.log(`   rows without canonical_project_id: ${noPid}`);

  const projects = projectRows.map(mapRowToProject);
  const isPinned = (name: string) => priorityProjectRankByName(name) >= 0;

  // ---- phase / confidence distribution ----
  const phaseDist: Record<string, number> = {};
  const confDist: Record<string, number> = {};
  for (const p of projects) {
    const ph = p.phase ?? "Unknown";
    phaseDist[ph] = (phaseDist[ph] ?? 0) + 1;
    const c = p.confidence ?? "?";
    confDist[c] = (confDist[c] ?? 0) + 1;
  }
  console.log("\n== projects phase distribution:", phaseDist);
  console.log("== projects confidence distribution:", confDist);

  const highActive = projects.filter(
    (p) => p.confidence === "high" && !["Delivery", "Commissioning"].includes(p.phase ?? ""),
  );
  console.log(`\n== high-confidence in-progress projects (excl Delivery/Commissioning): ${highActive.length}`);
  for (const p of highActive.slice(0, 20)) console.log(`   ${p.name}  [${p.phase}]`);

  // ---- Dashboard default order (no filters, showAllProjects=true) ----
  const scored = new Map<Project, number>();
  for (const p of projects) {
    try {
      scored.set(p, scoreOpportunity(p).totalScore);
    } catch {
      scored.set(p, -1);
    }
  }
  const pinnedFirst = sortPriorityFirst(projects, (p) => priorityProjectRankByName(p.name));
  const pinned = pinnedFirst.filter((p) => isPinned(p.name));
  const rest = pinnedFirst.filter((p) => !isPinned(p.name));
  rest.sort((a, b) => {
    const diff = (scored.get(b) ?? -1) - (scored.get(a) ?? -1);
    return diff !== 0 ? diff : a.name.localeCompare(b.name);
  });
  const dashOrder = [...pinned, ...rest];
  console.log(`\n== Dashboard default order: first 3 =`);
  for (const p of dashOrder.slice(0, 3)) console.log(`   ${p.name}  score=${scored.get(p)}  [${p.phase}] ${p.confidence}`);
  console.log("   positions 4-15:");
  dashOrder.slice(3, 15).forEach((p, i) =>
    console.log(`   #${i + 4}  score=${scored.get(p)}  ${p.name}  [${p.phase}] ${p.confidence}  ${/UK|United Kingdom/i.test(p.country) ? "UK" : p.country}`),
  );
  console.log("   noise positions:");
  dashOrder.forEach((p, i) => {
    if (NOISE_NAMES.some((n) => p.name.toUpperCase().includes(n)))
      console.log(`     #${i + 1}  ${p.name}  score=${scored.get(p)}`);
  });

  const ukCount = dashOrder.filter((p) => /UK|United Kingdom/i.test(p.country)).length;
  const ukTop20 = dashOrder.slice(0, 20).filter((p) => /UK|United Kingdom/i.test(p.country)).length;
  console.log(`   UK total in dashboard: ${ukCount}/${dashOrder.length}, UK in top-20: ${ukTop20}`);

  // ---- Battle Cards exact pipeline ----
  const hasPhase = (p: Project) => p.phase != null && p.phase !== PHASE_UNKNOWN;
  const battleCards = projects
    .filter((p) => hasPhase(p) && hasTimelineData(p, allEventCounts))
    .map((p) => ({ p, score: scored.get(p) ?? -1 }))
    .filter((item) => {
      if (isPinned(item.p.name)) return true;
      if (item.p.phase === "Delivery" || item.p.phase === "Commissioning") return false;
      return (item.score ?? -1) >= 55;
    })
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  const battleOrder = sortPriorityFirst(battleCards, (item) => priorityProjectRankByName(item.p.name));
  console.log(`\n== Battle Cards exact pipeline: ${battleOrder.length} cards`);
  console.log("   first 3:");
  for (const item of battleOrder.slice(0, 3))
    console.log(`     ${item.p.name}  score=${item.score}  [${item.p.phase}] ${item.p.confidence}`);
  console.log("   full list:");
  battleOrder.forEach((item, i) =>
    console.log(`     #${i + 1}  score=${item.score}  ${item.p.name}  [${item.p.phase}] ${item.p.confidence}`),
  );

  // ---- Timeline page: accepted-only counts ----
  const acceptedProjects = projects.filter(
    (p) => (acceptedEventCounts.get(normalizeProjectName(p.name) ?? "") ?? 0) > 0,
  );
  console.log(`\n== Timeline: projects with >=1 ACCEPTED event: ${acceptedProjects.length}`);
  console.log("   pinned three accepted counts:");
  for (const p of projects.filter((q) => PINNED_RE.test(q.name)))
    console.log(`     ${p.name}: accepted=${acceptedEventCounts.get(normalizeProjectName(p.name) ?? "") ?? 0} all=${allEventCounts.get(normalizeProjectName(p.name) ?? "") ?? 0}`);
  const zeroAccepted = projects.filter(
    (p) => (acceptedEventCounts.get(normalizeProjectName(p.name) ?? "") ?? 0) === 0,
  );
  console.log(`   zero-accepted (待挖掘) count: ${zeroAccepted.length}`);
}

main();
