/**
 * usePushAnalysis — AI-personalized analysis with instant rule-engine display.
 * ============================================================================
 *
 * The rule-engine result (rulesFallback) renders immediately so the UI never
 * waits on the LLM; when analyzePush() resolves, the AI result replaces it.
 * Pass `enabled: false` to skip the LLM call (e.g. cards below the fold) —
 * the rule-engine display still shows.
 */

import { useEffect, useState } from "react";
import type { Project } from "@/data/projects";
import { analyzePush, rulesFallback, type PushAnalysis } from "@/lib/push_analyst";

export function usePushAnalysis(
  project: Project | null | undefined,
  enabled = true,
): PushAnalysis | null {
  const [analysis, setAnalysis] = useState<PushAnalysis | null>(() =>
    project ? rulesFallback(project) : null,
  );
  const projectName = project?.name ?? null;

  useEffect(() => {
    if (!project) {
      setAnalysis(null);
      return;
    }
    let cancelled = false;
    setAnalysis(rulesFallback(project));
    if (!enabled) return;
    analyzePush(project).then((a) => {
      if (!cancelled) setAnalysis(a);
    });
    return () => {
      cancelled = true;
    };
  }, [projectName, enabled]);

  return analysis;
}
