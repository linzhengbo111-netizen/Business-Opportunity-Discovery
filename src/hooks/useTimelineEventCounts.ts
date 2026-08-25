/**
 * Fetches candidate_events and builds a Map<canonical_project_id, count>
 * for timeline coverage / maturity classification. Cached per page via
 * the realtime `version` (re-fetches when the projects table changes).
 */

import { useEffect, useState } from "react";
import { fetchAllRows } from "@/db/supabase";

export function useTimelineEventCounts(version: number): Map<string, number> {
  const [counts, setCounts] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    let cancelled = false;

    async function fetchCounts() {
      // Paginated loop fetch — plain select caps at 1000 rows.
      // 只统计 accepted 事件：时间线仅展示 accepted，rejected/pending 是噪音，
      // 计数与时间线保持一致。
      const { data, error } = await fetchAllRows(
        "candidate_events",
        "canonical_project_id, review_status",
        { orderBy: "id", notNullColumn: "canonical_project_id" },
      );

      if (cancelled || error || !data) return;

      const map = new Map<string, number>();
      for (const row of data) {
        if (String(row.review_status ?? "").toLowerCase() !== "accepted") continue;
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
