/**
 * useAllProjects — shared full project list for the top-bar global search.
 *
 * All three pages (商机看板 / 战报中心 / 项目时间线) mount the same Header,
 * so the list is cached at module level: one Supabase fetch per session,
 * refetched when the projects table changes via Realtime.
 */

import { useEffect, useState } from "react";
import type { Project } from "@/data/projects";
import { sampleProjects, COUNTRY_ALIASES, normalizeIndustry } from "@/data/projects";
import { normalizeProjectName, getDisplayName } from "@/data/project_aliases";
import { fetchAllRows } from "@/db/supabase";
import { useProjectRealtime } from "@/hooks/useProjectRealtime";
import { phaseFromRow } from "@/lib/project_phase";
import { parseCorrosiveMedia } from "@/lib/material_matcher";

let cache: Project[] | null = null;
let inflight: Promise<Record<string, unknown>[]> | null = null;

function normalizeCountry(raw: string): string {
  if (!raw) return "Unknown";
  const trimmed = raw.trim();
  return COUNTRY_ALIASES[trimmed] ?? COUNTRY_ALIASES[trimmed.toLowerCase()] ?? trimmed;
}

/** Parse a nullable int column from Supabase row. */
function toNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Parse a nullable text column from Supabase row. */
function toStr(v: unknown): string | null {
  if (v == null || v === "") return null;
  const s = String(v).trim();
  return s || null;
}

/** Map a raw Supabase row (snake_case columns) to the camelCase Project interface. */
function mapRowToProject(row: Record<string, unknown>): Project {
  const rawCountry = String(row.country ?? "").trim();
  const country = normalizeCountry(rawCountry);
  const rawName = String(row.name ?? "");
  // Normalize project name through canonical alias system for dedup
  const canonicalId = normalizeProjectName(rawName);
  const name = canonicalId ? getDisplayName(canonicalId) : rawName;
  const confidence = String(row.confidence ?? "medium") as "high" | "medium" | "low";
  return {
    name,
    country,
    flag: String(row.flag ?? ""),
    phase: phaseFromRow(row),
    summary: String(row.summary ?? ""),
    source: {
      name: String(row.source_name ?? ""),
      url: String(row.source_url ?? ""),
      date: String(row.source_date ?? ""),
    },
    stainlessSteel: String(row.stainless_steel ?? ""),
    application: String(row.application ?? ""),
    industry: normalizeIndustry(toStr(row.industry)),
    confidence,
    procurementChain: String(row.procurement_chain ?? ""),
    // Technical specs
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

export function useAllProjects(): Project[] {
  const [projects, setProjects] = useState<Project[]>(cache ?? []);
  const { version } = useProjectRealtime();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!inflight) {
        inflight = (async () => {
          const { data, error } = await fetchAllRows("projects", "*", { orderBy: "name" });
          if (error) throw error;
          return data ?? [];
        })();
      }
      try {
        const rows = await inflight;
        inflight = null;
        const mapped = rows.map(mapRowToProject);
        cache = mapped.length > 0 ? mapped : sampleProjects;
      } catch (err) {
        console.error(`[Header] projects fetch FAILED: ${(err as Error).message}`);
        cache = sampleProjects;
        inflight = null;
      }
      if (!cancelled) setProjects(cache);
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [version]);

  return projects;
}
