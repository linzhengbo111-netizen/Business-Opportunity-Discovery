/**
 * Diagnostic: rank the three formerly-pinned FPSO projects under the new
 * BattleCards filter (Commissioning excluded, Delivery allowed, score >= 55).
 * Usage: npx -y tsx scripts/rank_battlecards.ts
 */
import { scoreOpportunity } from "@/lib/opportunity_scorer";
import { phaseFromRow, PHASE_UNKNOWN } from "@/lib/project_phase";
import { parseCorrosiveMedia } from "@/lib/material_matcher";
import { COUNTRY_ALIASES } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import type { Project } from "@/data/projects";

const SUPABASE_URL = "https://zbxogsfnhagcavbvhypk.supabase.co";
const KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y";

const PINNED_IDS = new Set([
  "brazil-almirante-tamandare",
  "brazil-bacalhau",
  "brazil-sepetiba",
]);

function normalizeCountry(raw: string): string {
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  for (const [alias, canonical] of Object.entries(COUNTRY_ALIASES)) {
    if (lower === alias.toLowerCase()) return canonical;
  }
  return trimmed;
}

function toNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function toStr(v: unknown): string | null {
  if (v == null || v === "") return null;
  const s = String(v).trim();
  return s || null;
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

async function fetchAllRows(table: string, orderBy: string): Promise<Record<string, unknown>[]> {
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
    fetchAllRows("projects", "name.asc"),
    fetchAllRows("candidate_events", "id.asc"),
  ]);

  // Accepted-event counts per canonical id — mirrors useTimelineEventCounts
  const eventCounts = new Map<string, number>();
  for (const row of eventRows) {
    if (String(row.review_status ?? "").toLowerCase() !== "accepted") continue;
    const pid = String(row.canonical_project_id ?? "").trim();
    if (!pid) continue;
    eventCounts.set(pid, (eventCounts.get(pid) ?? 0) + 1);
  }

  const cards: {
    project: Project;
    canonicalId: string | null;
    score: number;
    grade: string;
  }[] = [];

  for (const row of projectRows) {
    const project = mapRowToProject(row);
    const hasPhase = project.phase != null && project.phase !== PHASE_UNKNOWN;
    const canonicalId = normalizeProjectName(String(row.name ?? ""));
    const events = canonicalId ? (eventCounts.get(canonicalId) ?? 0) : 0;
    if (!hasPhase || events < 1) continue;
    if (project.phase === "Commissioning") continue;
    const r = scoreOpportunity(project);
    if (r.totalScore < 55) continue;
    cards.push({ project, canonicalId, score: r.totalScore, grade: r.grade });
  }

  cards.sort((a, b) => b.score - a.score);
  console.log(`visible cards: ${cards.length}`);
  console.log("");

  for (let i = 0; i < cards.length; i++) {
    const c = cards[i];
    const pinned = c.canonicalId != null && PINNED_IDS.has(c.canonicalId);
    const mark = pinned ? "  <<< 原置顶" : "";
    console.log(
      `#${i + 1}  ${c.score}  ${c.grade}  ${c.project.phase.padEnd(14)} ${c.project.name}${mark}`,
    );
  }

  const pinnedRanks = cards
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.canonicalId != null && PINNED_IDS.has(c.canonicalId));
  console.log("");
  for (const { c, i } of pinnedRanks) {
    console.log(
      `原置顶项目 ${c.project.name}: 评分 ${c.score} (${c.grade}), 排名 #${i + 1} / ${cards.length}`,
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
