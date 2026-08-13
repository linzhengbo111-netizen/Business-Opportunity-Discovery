/**
 * Fetches candidate_events and builds a Map<canonical_project_id, count>
 * for timeline coverage / maturity classification. Cached per page via
 * the realtime `version` (re-fetches when the projects table changes).
 */

import { useEffect, useState } from "react";
import { supabase } from "@/db/supabase";

export function useTimelineEventCounts(version: number): Map<string, number> {
  const [counts, setCounts] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    let cancelled = false;

    async function fetchCounts() {
      const { data, error } = await supabase
        .from("candidate_events")
        .select("canonical_project_id")
        .not("canonical_project_id", "is", null);

      if (cancelled || error || !data) return;

      const map = new Map<string, number>();
      for (const row of data) {
        const pid = String(row.canonical_project_id ?? "").trim();
        if (!pid) continue;
        map.set(pid, (map.get(pid) ?? 0) + 1);
      }
      if (!cancelled) setCounts(map);
    }

    fetchCounts();

    return () => {
      cancelled = true;
    };
  }, [version]);

  return counts;
}
