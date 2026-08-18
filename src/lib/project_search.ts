/**
 * Global project search — case-insensitive, accent-insensitive substring
 * matching across the fields the sales team actually looks up:
 * project name, country, field (油田), operator (运营商), procurement chain.
 */

import type { Project } from "@/data/projects";

/** Searchable field keys and their Chinese display labels. */
export const SEARCH_FIELD_LABELS: Record<string, string> = {
  name: "项目",
  country: "国家",
  fieldName: "油田",
  operatorName: "运营商",
  procurementChain: "采购链",
};

export interface ProjectSearchMatch {
  project: Project;
  /** Searchable field keys that matched (see SEARCH_FIELD_LABELS). */
  fields: string[];
}

/** Lowercase + strip diacritics so "Búzios" matches "buzios". */
function normalizeForSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function searchableEntries(p: Project): [string, string][] {
  return [
    ["name", p.name],
    ["country", p.country],
    ["fieldName", p.fieldName ?? ""],
    ["operatorName", p.operatorName ?? ""],
    ["procurementChain", p.procurementChain ?? ""],
  ];
}

/**
 * Fuzzy search over the in-memory project list.
 * Name matches rank first, then field, country, operator, procurement.
 */
export function searchProjects(
  projects: Project[],
  query: string,
): ProjectSearchMatch[] {
  const q = normalizeForSearch(query);
  if (!q) return [];

  const tokens = q.split(/\s+/).filter(Boolean);

  const results: ProjectSearchMatch[] = [];
  for (const p of projects) {
    const entries = searchableEntries(p);
    const matched: string[] = [];

    for (const [key, raw] of entries) {
      if (!raw) continue;
      const norm = normalizeForSearch(raw);
      // Whole-query substring, or every token present in this field.
      if (norm.includes(q) || (tokens.length > 1 && tokens.every((t) => norm.includes(t)))) {
        matched.push(key);
      }
    }

    if (matched.length === 0) continue;
    results.push({ project: p, fields: matched });
  }

  // Name matches first, then field / country / operator / procurement.
  const rank: Record<string, number> = {
    name: 0,
    fieldName: 1,
    country: 2,
    operatorName: 3,
    procurementChain: 4,
  };
  results.sort((a, b) => {
    const ra = Math.min(...a.fields.map((f) => rank[f] ?? 9));
    const rb = Math.min(...b.fields.map((f) => rank[f] ?? 9));
    if (ra !== rb) return ra - rb;
    return a.project.name.localeCompare(b.project.name);
  });

  return results;
}

/** Whether a single project matches the query (used for list filtering). */
export function projectMatchesSearch(project: Project, query: string): boolean {
  const q = normalizeForSearch(query);
  if (!q) return true;
  const tokens = q.split(/\s+/).filter(Boolean);
  return searchableEntries(project).some(([, raw]) => {
    if (!raw) return false;
    const norm = normalizeForSearch(raw);
    return norm.includes(q) || (tokens.length > 1 && tokens.every((t) => norm.includes(t)));
  });
}
