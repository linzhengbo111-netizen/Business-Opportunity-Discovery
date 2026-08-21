/**
 * usePushAnalysis — AI-personalized analysis with instant rule-engine display.
 * ============================================================================
 *
 * While the LLM call is in flight, `analysis` is null and `loading` is true —
 * callers show an "AI 分析中…" indicator instead of rule content. When
 * analyzePush() resolves, the AI result replaces it; on failure the rule
 * fallback arrives with `loading: false` (and analyzePush logs the reason).
 * Pass `enabled: false` to skip the LLM call (e.g. cards below the fold) —
 * the rule-engine display still shows immediately.
 */

import { useEffect, useState } from "react";
import type { Project } from "@/data/projects";
import { analyzePush, rulesFallback, type PushAnalysis } from "@/lib/push_analyst";

export interface PushAnalysisState {
  /** Current analysis — null while the LLM call is in flight. */
  analysis: PushAnalysis | null;
  /** True while the LLM call is in flight — show a loading indicator. */
  loading: boolean;
}

/**
 * Stateful variant — exposes `loading` so callers can show "AI 分析中…"
 * instead of rule-engine content while the LLM call is in flight.
 */
export function usePushAnalysisState(
  project: Project | null | undefined,
  enabled = true,
): PushAnalysisState {
  const projectName = project?.name ?? null;
  const [state, setState] = useState<PushAnalysisState>(() => {
    if (!project) return { analysis: null, loading: false };
    return enabled
      ? { analysis: null, loading: true }
      : { analysis: rulesFallback(project), loading: false };
  });

  useEffect(() => {
    if (!project) {
      setState({ analysis: null, loading: false });
      return;
    }
    let cancelled = false;
    if (!enabled) {
      setState({ analysis: rulesFallback(project), loading: false });
      return;
    }
    setState({ analysis: null, loading: true });
    analyzePush(project).then((a) => {
      if (!cancelled) setState({ analysis: a, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [projectName, enabled]);

  return state;
}

/**
 * Back-compatible accessor — the current analysis (null while the LLM call
 * is in flight; the rule-engine fallback once it settles on failure).
 */
export function usePushAnalysis(
  project: Project | null | undefined,
  enabled = true,
): PushAnalysis | null {
  return usePushAnalysisState(project, enabled).analysis;
}
