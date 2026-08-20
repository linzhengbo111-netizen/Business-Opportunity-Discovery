/**
 * One-off backfill: recompute projects.opportunity_score with the live
 * scoring engine (src/lib/opportunity_scorer.ts — the same code the
 * battle cards / dashboard recompute at render time) and write changed
 * rows back to Supabase.
 *
 * Reason: phase correction (Construction → Delivery) changed the scorer
 * input for many rows, but the stored opportunity_score JSONB was never
 * recomputed, leaving stale grades/reasoning in the DB.
 *
 * Usage:
 *   npx tsx scripts/backfill_opportunity_scores.ts            # dry run
 *   npx tsx scripts/backfill_opportunity_scores.ts --execute  # write
 */

import * as fs from "node:fs";
import * as path from "node:path";

import type { Project } from "../src/data/projects";
import { scoreOpportunity } from "../src/lib/opportunity_scorer";

// ---- Config (parse .env manually — no dotenv dep in root package) -------

function loadEnv(): Record<string, string> {
  const envPath = path.resolve(process.cwd(), ".env");
  const out: Record<string, string> = {};
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}

const env = loadEnv();
const SUPABASE_URL = env.VITE_SUPABASE_URL;
const SUPABASE_KEY = env.VITE_SUPABASE_ANON_KEY;
if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error("VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY missing in .env");
  process.exit(1);
}

const EXECUTE = process.argv.includes("--execute");
const PAGE_SIZE = 1000;

const SELECT_COLS = [
  "id", "name", "country", "flag", "phase", "summary",
  "source_name", "source_url", "source_date", "stainless_steel",
  "application", "industry", "confidence", "procurement_chain",
  "water_depth_m", "oil_capacity_bpd", "gas_capacity_mmcmd",
  "hull_type", "field_name", "operator_name", "basin",
  "recommendation_json", "created_at", "opportunity_score",
].join(",");

// ---- Supabase REST helpers ------------------------------------------------

async function fetchPage(offset: number): Promise<Record<string, unknown>[]> {
  const url = `${SUPABASE_URL}/rest/v1/projects?select=${SELECT_COLS}&order=id.asc&limit=${PAGE_SIZE}&offset=${offset}`;
  const res = await fetch(url, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!res.ok) {
    throw new Error(`fetch failed ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as Record<string, unknown>[];
}

async function fetchAll(): Promise<Record<string, unknown>[]> {
  const all: Record<string, unknown>[] = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const page = await fetchPage(offset);
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
  }
  return all;
}

async function updateRow(id: number, opportunityScore: unknown): Promise<void> {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/projects?id=eq.${id}`,
    {
      method: "PATCH",
      headers: {
        apikey: SUPABASE_KEY,
        Authorization: `Bearer ${SUPABASE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({ opportunity_score: opportunityScore }),
    },
  );
  if (!res.ok) {
    throw new Error(`PATCH id=${id} failed ${res.status}: ${await res.text()}`);
  }
}

// ---- Row → Project mapping (mirrors the app's supabase row mapper) --------

function rowToProject(r: Record<string, unknown>): Project {
  return {
    name: String(r.name ?? ""),
    country: String(r.country ?? ""),
    flag: String(r.flag ?? ""),
    phase: r.phase == null ? null : String(r.phase),
    summary: String(r.summary ?? ""),
    source: {
      name: String(r.source_name ?? ""),
      url: String(r.source_url ?? ""),
      date: String(r.source_date ?? ""),
    },
    stainlessSteel: String(r.stainless_steel ?? ""),
    application: String(r.application ?? ""),
    industry: r.industry == null ? undefined : String(r.industry),
    confidence: (r.confidence as Project["confidence"]) ?? undefined,
    procurementChain: r.procurement_chain == null ? undefined : String(r.procurement_chain),
    waterDepthM: (r.water_depth_m as number | null) ?? null,
    oilCapacityBpd: (r.oil_capacity_bpd as number | null) ?? null,
    gasCapacityMmcmd: (r.gas_capacity_mmcmd as number | null) ?? null,
    hullType: (r.hull_type as string | null) ?? null,
    fieldName: (r.field_name as string | null) ?? null,
    operatorName: (r.operator_name as string | null) ?? null,
    basin: (r.basin as string | null) ?? null,
    recommendationJson: (r.recommendation_json as string | null) ?? null,
    createdAt: (r.created_at as string | null) ?? null,
  };
}

interface StoredScore {
  totalScore?: number;
  grade?: string;
  dimensions?: Record<string, { score?: number }>;
}

/** Compare new score against stored JSONB — changed if totals or any dimension differ. */
function scoreChanged(stored: StoredScore | null, fresh: ReturnType<typeof scoreOpportunity>): boolean {
  if (!stored) return true;
  if (stored.totalScore !== fresh.totalScore || stored.grade !== fresh.grade) return true;
  for (const [key, dim] of Object.entries(fresh.dimensions)) {
    if (stored.dimensions?.[key]?.score !== dim.score) return true;
  }
  return false;
}

// ---- Main -----------------------------------------------------------------

async function main() {
  const rows = await fetchAll();
  console.log(`fetched ${rows.length} rows (mode: ${EXECUTE ? "execute" : "dry-run"})`);

  let changed = 0;
  let changedWithPriorScore = 0;
  let written = 0;
  let errors = 0;
  const changedRows: { id: number; name: string; old: string; fresh: string }[] = [];

  for (const row of rows) {
    const project = rowToProject(row);
    let fresh: ReturnType<typeof scoreOpportunity>;
    try {
      fresh = scoreOpportunity(project);
    } catch (err) {
      console.error(`score failed id=${row.id} ${row.name}: ${err}`);
      errors++;
      continue;
    }

    const stored = (row.opportunity_score ?? null) as StoredScore | null;
    if (!scoreChanged(stored, fresh)) continue;

    changed++;
    if (stored) changedWithPriorScore++;
    const oldDesc = stored
      ? `${stored.totalScore}/${stored.grade} (proc ${stored.dimensions?.procurement?.score})`
      : "NULL";
    const freshDesc = `${fresh.totalScore}/${fresh.grade} (proc ${fresh.dimensions.procurement.score})`;
    changedRows.push({ id: Number(row.id), name: String(row.name), old: oldDesc, fresh: freshDesc });

    if (EXECUTE) {
      try {
        await updateRow(Number(row.id), fresh);
        written++;
      } catch (err) {
        console.error(`write failed id=${row.id}: ${err}`);
        errors++;
      }
    }
  }

  // Summary: show the three demo FPSOs first, then the rest.
  const demo = changedRows.filter((r) =>
    /TAMANDARE|BACALHAU|SEPETIBA/.test(r.name.toUpperCase()));
  const rest = changedRows.filter((r) =>
    !/TAMANDARE|BACALHAU|SEPETIBA/.test(r.name.toUpperCase()));
  console.log(`\nchanged: ${changed} (with prior score: ${changedWithPriorScore}, from NULL: ${changed - changedWithPriorScore}) | ${EXECUTE ? `written: ${written}` : "writes skipped (dry run)"} | errors: ${errors}`);
  console.log("\n--- demo FPSOs ---");
  for (const r of demo) console.log(`  ${r.name}: ${r.old} -> ${r.fresh}`);
  console.log(`--- other ${rest.length} rows ---`);
  for (const r of rest.slice(0, 30)) console.log(`  [${r.id}] ${r.name}: ${r.old} -> ${r.fresh}`);
  if (rest.length > 30) console.log(`  ... and ${rest.length - 30} more`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
