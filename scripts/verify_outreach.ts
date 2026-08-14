/**
 * One-off verification for generate_outreach_message (S9).
 *
 * Runs the REAL ai_analyst.ts code (via tsx) against a local `wrangler dev`
 * worker on port 8787 (LLM_API_KEY provided via temporary .dev.vars).
 * Fetches the FPSO ALMIRANTE TAMANDARE row from Supabase, generates the
 * outreach email, and checks that required facts appear and that no
 * fabricated credentials/contacts are present.
 *
 * Usage:
 *   npx tsx scripts/verify_outreach.ts
 */

import { readFileSync } from "node:fs";
import { createClient } from "@supabase/supabase-js";
import { generate_outreach_message } from "../src/lib/ai_analyst";
import type { Project } from "../src/data/projects";

// ---- Load .env (no dotenv dependency in root) -----------------------------
for (const line of readFileSync(new URL("../.env", import.meta.url), "utf8").split("\n")) {
  const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
  if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
}

// ---- Redirect relative /api/llm fetches to the local worker ---------------
const realFetch = globalThis.fetch;
(globalThis as unknown as { fetch: typeof fetch }).fetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  if (url === "/api/llm" || url === "/api/llm/status") {
    return realFetch(`http://127.0.0.1:8787${url}`, init);
  }
  return realFetch(input, init);
};

// ---- Map a Supabase row onto the frontend Project shape -------------------
function rowToProject(row: Record<string, unknown>): Project {
  return {
    name: String(row.name ?? ""),
    country: String(row.country ?? ""),
    flag: String(row.flag ?? ""),
    status: String(row.status ?? ""),
    summary: String(row.summary ?? ""),
    source: {
      name: String(row.source_name ?? ""),
      url: String(row.source_url ?? ""),
      date: String(row.publication_date ?? ""),
    },
    stainlessSteel: String(row.stainless_steel ?? ""),
    application: String(row.application ?? ""),
    industry: typeof row.industry === "string" ? row.industry : undefined,
    confidence: ["high", "medium", "low"].includes(String(row.confidence))
      ? (String(row.confidence) as "high" | "medium" | "low")
      : undefined,
    procurementChain: typeof row.procurement_chain === "string" ? row.procurement_chain : undefined,
    waterDepthM: row.water_depth_m != null ? Number(row.water_depth_m) : null,
    oilCapacityBpd: row.oil_capacity_bpd != null ? Number(row.oil_capacity_bpd) : null,
    gasCapacityMmcmd: row.gas_capacity_mmcmd != null ? Number(row.gas_capacity_mmcmd) : null,
    hullType: typeof row.hull_type === "string" ? row.hull_type : null,
    fieldName: typeof row.field_name === "string" ? row.field_name : null,
    operatorName: typeof row.operator_name === "string" ? row.operator_name : null,
    basin: typeof row.basin === "string" ? row.basin : null,
    recommendationJson: typeof row.recommendation_json === "string" ? row.recommendation_json : null,
    corrosiveMedia: (row.corrosive_media as Record<string, unknown> | null) ?? null,
  };
}

// ---- Main ------------------------------------------------------------------
async function main() {
  const url = process.env.VITE_SUPABASE_URL;
  const key = process.env.VITE_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY missing in .env");

  const supabase = createClient(url, key);
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("name", "FPSO ALMIRANTE TAMANDARE");
  if (error) throw new Error(`Supabase error: ${error.message}`);
  if (!data || data.length === 0) throw new Error("Project not found in Supabase");
  const row = data[0] as Record<string, unknown>;
  console.log("Project row:", JSON.stringify(
    { name: row.name, country: row.country, procurement_chain: row.procurement_chain,
      operator_name: row.operator_name, basin: row.basin, water_depth_m: row.water_depth_m,
      recommendation_json: row.recommendation_json, stainless_steel: row.stainless_steel },
    null, 2));

  const result = await generate_outreach_message(rowToProject(row));
  if (!result) {
    console.error("RESULT: null — generation failed");
    process.exit(1);
  }

  console.log("===== SUBJECT =====");
  console.log(result.subject);
  console.log("===== BODY =====");
  console.log(result.body);

  // ---- Required-fact checks ----
  const full = `${result.subject}\n${result.body}`;
  const checks: Array<[string, boolean]> = [
    ["Super Duplex 2507 mentioned", /2507/i.test(full)],
    ["SBM Offshore mentioned", /SBM Offshore/i.test(full)],
    ["Brazil pre-salt / Santos Basin mentioned", /pre-salt|pré-sal|Santos Basin/i.test(full)],
    ["No fabricated ISO cert number", !/ISO\s?\d{4,5}/.test(full)],
    ["No fabricated certification claim (ISO/API/ASME)", !/ISO\s?9001|API\s?5L|ASME/i.test(full)],
  ];
  let allOk = true;
  for (const [label, ok] of checks) {
    console.log(`${ok ? "PASS" : "FAIL"} — ${label}`);
    if (!ok) allOk = false;
  }
  console.log(allOk ? "===== ALL CHECKS PASSED =====" : "===== CHECKS FAILED =====");
  process.exit(allOk ? 0 : 1);
}

main().catch((err) => {
  console.error("Verify failed:", err);
  process.exit(1);
});
