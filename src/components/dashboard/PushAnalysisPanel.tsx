/**
 * PushAnalysisPanel — shared rendering for AI-personalized analysis
 * ==================================================================
 *
 * Renders the same analysis the Feishu push card shows: procurement window
 * with reasoning, recommended materials and products with per-item reasons,
 * plus the source tag (AI 推断 / 规则引擎). Used by the Dashboard detail
 * modal and the Database slide-out panel so both stay identical.
 */

import type { PushAnalysis } from "@/lib/push_analyst";

/** Marks whether the content came from the LLM or the rule engine. */
export function PushSourceBadge({ source }: { source: "ai" | "rules" }) {
  return source === "ai" ? (
    <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-green/15 px-1.5 py-0.5 text-[10px] font-semibold text-fpso-green">
      AI 推断
    </span>
  ) : (
    <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-muted/15 px-1.5 py-0.5 text-[10px] font-semibold text-fpso-muted">
      规则引擎
    </span>
  );
}

function confidenceClass(confidence: string): string {
  switch (confidence) {
    case "high":
      return "bg-fpso-green/15 text-fpso-green";
    case "medium":
      return "bg-fpso-orange/15 text-fpso-orange";
    default:
      return "bg-fpso-muted/15 text-fpso-muted";
  }
}

const CONFIDENCE_LABELS: Record<string, string> = { high: "高", medium: "中", low: "低" };

interface PushAnalysisPanelProps {
  analysis: PushAnalysis | null;
  /** Show the AI 分析摘要 block when the AI result carries one (default true). */
  showSummary?: boolean;
  className?: string;
}

export default function PushAnalysisPanel({
  analysis,
  showSummary = true,
  className,
}: PushAnalysisPanelProps) {
  if (!analysis) {
    return <p className="text-xs italic text-fpso-dim">AI 分析中…</p>;
  }

  const { procurement_window: pw, recommended_materials: mats, recommended_products: prods } =
    analysis;
  const hasAny = pw.range !== "待补充" || mats.length > 0 || prods.length > 0;
  if (!hasAny) {
    return <span className="text-fpso-dim italic">暂无数据</span>;
  }

  return (
    <div className={className ?? "space-y-3"}>
      {/* 采购时间窗 */}
      {pw.range !== "待补充" && (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-fpso-muted">采购时间窗:</span>
            <span className="rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-semibold text-fpso-blue">
              {pw.range}
            </span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${confidenceClass(pw.confidence)}`}>
              置信度 {CONFIDENCE_LABELS[pw.confidence] ?? pw.confidence}
            </span>
            <PushSourceBadge source={analysis.source} />
          </div>
          {pw.reasoning && (
            <p className="mt-1 text-[11px] leading-relaxed text-fpso-dim italic">{pw.reasoning}</p>
          )}
        </div>
      )}

      {/* 推荐材质 — 每条附理由 */}
      {mats.length > 0 && (
        <div>
          <span className="text-xs text-fpso-muted">推荐材质:</span>
          <div className="mt-1 space-y-1">
            {mats.map((m) => (
              <div key={m.grade} className="flex items-start gap-2">
                <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-mono font-medium text-fpso-blue">
                  {m.grade}
                </span>
                {m.reason && (
                  <span className="text-[11px] leading-relaxed text-fpso-dim">{m.reason}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 推荐产品 — 每条附理由 */}
      {prods.length > 0 && (
        <div>
          <span className="text-xs text-fpso-muted">推荐产品:</span>
          <div className="mt-1 space-y-1">
            {prods.map((p) => (
              <div key={p.product} className="flex items-start gap-2">
                <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-orange/10 px-2 py-0.5 text-xs font-medium text-fpso-orange">
                  {p.product}
                </span>
                {p.reason && (
                  <span className="text-[11px] leading-relaxed text-fpso-dim">{p.reason}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI 分析摘要 — 与飞书推送卡片一致 */}
      {showSummary && analysis.source === "ai" && analysis.ai_summary && (
        <div className="rounded-md border border-fpso-green/15 bg-fpso-green/[0.05] p-2.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-fpso-dim">
            AI 分析摘要
          </span>
          <p className="mt-1 text-xs leading-relaxed text-fpso-fg/90">{analysis.ai_summary}</p>
        </div>
      )}
    </div>
  );
}
