import { createClient } from "@supabase/supabase-js";

const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)
  || "https://zbxogsfnhagcavbvhypk.supabase.co";
const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined)
  || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpieG9nc2ZuaGFnY2F2YnZoeXBrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1NTEzMzAsImV4cCI6MjEwMDEyNzMzMH0.lyhFL4J6O98pnjsL-oGZWPMvdN_j-xKe6Ol94-45z4Y";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/* ------------------------------------------------------------------ */
/*  Paginated fetch — Supabase caps a single query at 1000 rows.       */
/*  Loop with .range() so every row (1168+ projects) is covered.       */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 1000;
/** Hard safety cap — never loop past this many rows. */
const MAX_ROWS = 50_000;

export interface FetchAllRowsResult {
  data: Record<string, unknown>[];
  error: { message: string } | null;
}

interface FetchAllRowsOptions {
  /** Column to order by for stable pagination (default "id"). */
  orderBy?: string;
  ascending?: boolean;
  /** When set, adds `.not(column, "is", null)` to the query. */
  notNullColumn?: string;
}

/**
 * Fetch every row of a table in 1000-row pages.
 * Returns partial data plus the error if a page fails mid-loop.
 */
export async function fetchAllRows(
  table: "projects" | "candidate_events",
  select = "*",
  options: FetchAllRowsOptions = {},
): Promise<FetchAllRowsResult> {
  const { orderBy = "id", ascending = true, notNullColumn } = options;
  const rows: Record<string, unknown>[] = [];
  let from = 0;

  while (from < MAX_ROWS) {
    let query = supabase
      .from(table)
      .select(select)
      .order(orderBy, { ascending })
      .range(from, from + PAGE_SIZE - 1);
    if (notNullColumn) {
      query = query.not(notNullColumn, "is", null);
    }

    const { data, error } = await query;
    if (error) {
      return { data: rows, error };
    }
    const page = (data ?? []) as unknown as Record<string, unknown>[];
    if (page.length === 0) break;

    rows.push(...page);
    if (page.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { data: rows, error: null };
}
