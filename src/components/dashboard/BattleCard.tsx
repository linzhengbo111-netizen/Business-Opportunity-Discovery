/**
 * Sales Battle Card Component (S6)
 * =================================
 *
 * One-page battle card designed for printing, screenshot sharing,
 * and quick sales prep. Dark terminal theme matching the app.
 */

import { useRef, useCallback, useState, useEffect } from "react";
import { generateBattleCard, type BattleCard } from "@/lib/battle_card";
import type { Project } from "@/data/projects";
import { useFollowUp, FOLLOW_UP_STATUS_LABELS, type FollowUp } from "@/hooks/useFollowUp";
import { usePushAnalysisState } from "@/hooks/usePushAnalysis";
import { type AISource } from "@/lib/ai_analyst";
import type { PushAnalysis } from "@/lib/push_analyst";
import OutreachModal from "@/components/dashboard/OutreachModal";

// ---------------------------------------------------------------------------
// Grade colour helpers
// ---------------------------------------------------------------------------

function gradeColor(grade: string): string {
  switch (grade) {
    case "A": return "text-fpso-green";
    case "B": return "text-fpso-blue";
    case "C": return "text-fpso-orange";
    default:  return "text-fpso-muted";
  }
}

function gradeBg(grade: string): string {
  switch (grade) {
    case "A": return "bg-fpso-green/15 border-fpso-green/30";
    case "B": return "bg-fpso-blue/15 border-fpso-blue/30";
    case "C": return "bg-fpso-orange/15 border-fpso-orange/30";
    default:  return "bg-fpso-muted/15 border-fpso-muted/30";
  }
}

// ---------------------------------------------------------------------------
// Action button helpers
// ---------------------------------------------------------------------------

async function copyLink(url: string) {
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    // Fallback for older browsers / non-HTTPS
    const ta = document.createElement("textarea");
    ta.value = url;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

function handlePrint() {
  window.print();
}

/**
 * Capture a DOM element as a PNG data URL using html2canvas loaded from CDN.
 * Falls back gracefully if CDN is unreachable (offline use).
 */
async function elementToPng(element: HTMLElement): Promise<string | null> {
  // Load html2canvas from CDN on first call
  const H2C = (window as any).html2canvas;
  if (!H2C) {
    try {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("CDN unreachable"));
        document.head.appendChild(script);
      });
    } catch {
      return null; // offline — caller shows fallback message
    }
  }

  const h2c = (window as any).html2canvas;
  if (!h2c) return null;

  const canvas = await h2c(element, {
    backgroundColor: "#ffffff",
    scale: 2,
    useCORS: true,
    logging: false,
  });
  return canvas.toDataURL("image/png");
}

async function downloadPng(element: HTMLElement, filename: string) {
  try {
    const dataUrl = await elementToPng(element);
    if (!dataUrl) {
      alert("CDN unreachable (offline). Use Print → Save as PDF instead.");
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = dataUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(dataUrl);
  } catch (err) {
    console.error("Failed to generate PNG:", err);
    alert("PNG generation failed. Use Print → Save as PDF instead.");
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Marks whether a section's content came from the LLM or the rule engine. */
function SourceTag({ source }: { source: AISource }) {
  return (
    <span
      className={
        source === "ai"
          ? "inline-flex flex-shrink-0 items-center rounded bg-fpso-green/15 px-1.5 py-0.5 text-[9px] font-semibold text-fpso-green"
          : "inline-flex flex-shrink-0 items-center rounded bg-fpso-muted/15 px-1.5 py-0.5 text-[9px] font-semibold text-fpso-muted"
      }
    >
      {source === "ai" ? "AI 推断" : "规则引擎"}
    </span>
  );
}

function SectionHeader({ children, source }: { children: string; source?: AISource }) {
  return (
    <div className="mb-1.5 flex items-center justify-between gap-2">
      <h4 className="text-[11px] font-semibold uppercase tracking-widest text-fpso-dim/80">
        {children}
      </h4>
      {source && <SourceTag source={source} />}
    </div>
  );
}

function EmptyState() {
  return <span className="text-xs text-fpso-dim italic">—</span>;
}

// ---------------------------------------------------------------------------
// BattleCard (internal, render-only)
// ---------------------------------------------------------------------------

interface BattleCardViewProps {
  card: BattleCard;
  innerRef: React.Ref<HTMLDivElement>;
  followUp?: FollowUp | null;
  /** Timeline digest passed in by the page — 待补充 shown when absent. */
  timelineSummary?: string;
  /** AI-personalized analysis (same as the Feishu push) — replaces the rule
   *  results when available, rule engine stays as fallback. */
  analysis?: PushAnalysis | null;
  /** True while the LLM call is in flight — shows a loading banner. */
  analysisLoading?: boolean;
}

function BattleCardView({ card, innerRef, followUp, timelineSummary, analysis, analysisLoading }: BattleCardViewProps) {
  const showBanner = followUp && (followUp.status === "invalid" || followUp.status === "closed");
  return (
    <div
      ref={innerRef}
      className="battle-card w-full max-w-2xl mx-auto rounded-xl border border-border bg-fpso-card/60 backdrop-blur-md shadow-2xl overflow-hidden"
      style={{ minWidth: 600 }}
    >
      {/* ---- invalid / closed banner ---- */}
      {showBanner && (
        <div className={`px-4 py-2 text-center text-xs font-semibold ${
          followUp!.status === "invalid"
            ? "bg-fpso-muted/20 text-fpso-muted"
            : "bg-fpso-green/10 text-fpso-green"
        }`}>
          {followUp!.status === "invalid"
            ? "This project has been marked as Invalid — 已标记为无效商机"
            : "This project has been Closed — 已成交"}
        </div>
      )}

      {/* ---- top bar ---- */}
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border bg-fpso-bg/40">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-bold text-fpso-fg truncate">{card.projectName}</h2>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-fpso-muted">{card.country}</span>
            <span className="h-3 w-px bg-fpso-border/50" />
            <span className="text-xs text-fpso-muted">{card.phase}</span>
          </div>
        </div>
        <div className="flex flex-col items-end flex-shrink-0">
          <span
            className={`inline-flex items-center rounded-md border px-3 py-1 text-lg font-extrabold tracking-tight ${gradeBg(card.grade)} ${gradeColor(card.grade)}`}
          >
            {card.grade}
          </span>
          <span className="text-[10px] font-mono text-fpso-dim mt-0.5">
            {card.totalScore}/100
          </span>
        </div>
      </div>

      {/* ---- AI loading banner ---- */}
      {analysisLoading && (
        <div className="border-b border-border bg-amber-400/5 px-5 py-2 text-center text-xs font-medium text-amber-400 animate-pulse">
          AI 分析中… 结果返回后自动替换
        </div>
      )}

      {/* ---- body ---- */}
      <div className="grid grid-cols-2 gap-0">

        {/* ---- left column ---- */}
        <div className="p-4 space-y-4 border-r border-border">
          {/* why pursue */}
          <div>
            <SectionHeader>Why Pursue · 为什么值得追</SectionHeader>
            <p className="text-xs leading-relaxed text-fpso-fg/90">
              {card.whyPursue}
            </p>
          </div>

          {/* what to push — AI 结果优先，规则引擎兜底 */}
          {(() => {
            const useAi = analysis && analysis.recommended_products.length > 0;
            return (
              <div>
                <SectionHeader source={useAi ? analysis!.source : "rules"}>What to Push · 推荐产品</SectionHeader>
                {useAi ? (
                  <div className="space-y-1">
                    {analysis!.recommended_products.map((p) => (
                      <div key={p.product} className="flex items-start gap-1.5">
                        <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-medium text-fpso-blue border border-fpso-blue/15">
                          {p.product}
                        </span>
                        {p.reason && (
                          <span className="text-[10px] leading-relaxed text-fpso-dim">{p.reason}</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : card.whatToPush.length === 0 ? (
                  <EmptyState />
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {card.whatToPush.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center rounded bg-fpso-blue/10 px-2 py-0.5 text-xs font-medium text-fpso-blue border border-fpso-blue/15"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* material grades — AI 结果优先，规则引擎兜底 */}
          {(() => {
            const useAi = analysis && analysis.recommended_materials.length > 0;
            return (
              <div>
                <SectionHeader source={useAi ? analysis!.source : undefined}>Material Grades · 推荐牌号</SectionHeader>
                {useAi ? (
                  <div className="space-y-1">
                    {analysis!.recommended_materials.map((m) => (
                      <div key={m.grade} className="flex items-start gap-1.5">
                        <span className="inline-flex flex-shrink-0 items-center rounded bg-fpso-green/10 px-2 py-0.5 text-xs font-mono font-medium text-fpso-green border border-fpso-green/15">
                          {m.grade}
                        </span>
                        {m.reason && (
                          <span className="text-[10px] leading-relaxed text-fpso-dim">{m.reason}</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : card.materialGrades.length === 0 ? (
                  <EmptyState />
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {card.materialGrades.map((g) => (
                      <span
                        key={g}
                        className="inline-flex items-center rounded bg-fpso-green/10 px-2 py-0.5 text-xs font-mono font-medium text-fpso-green border border-fpso-green/15"
                      >
                        {g}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* timeline summary — basic cards still show a digest when available */}
          <div>
            <SectionHeader>Timeline · 时间线摘要</SectionHeader>
            {timelineSummary ? (
              <p className="text-xs leading-relaxed text-fpso-fg/90">{timelineSummary}</p>
            ) : (
              <span className="inline-flex items-center rounded bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-400 ring-1 ring-amber-400/20">
                待补充
              </span>
            )}
          </div>

          {/* AI 分析摘要 — 与飞书推送卡片一致，仅 AI 成功时展示 */}
          {analysis?.source === "ai" && analysis.ai_summary && (
            <div>
              <SectionHeader source="ai">AI 分析摘要</SectionHeader>
              <p className="text-xs leading-relaxed text-fpso-fg/90">{analysis.ai_summary}</p>
            </div>
          )}
        </div>

        {/* ---- right column ---- */}
        <div className="p-4 space-y-4">
          {/* who to contact */}
          <div>
            <SectionHeader>Who to Contact · 联系谁</SectionHeader>
            <div className="space-y-1 text-xs text-fpso-fg/90">
              {card.whoToContact.epcContractor && (
                <div className="flex gap-2">
                  <span className="text-fpso-dim flex-shrink-0">EPC:</span>
                  <span className="text-fpso-green font-medium">{card.whoToContact.epcContractor}</span>
                </div>
              )}
              {card.whoToContact.operator && (
                <div className="flex gap-2">
                  <span className="text-fpso-dim flex-shrink-0">运营商:</span>
                  <span>{card.whoToContact.operator}</span>
                </div>
              )}
              {card.whoToContact.owner && !card.whoToContact.operator && (
                <div className="flex gap-2">
                  <span className="text-fpso-dim flex-shrink-0">业主:</span>
                  <span>{card.whoToContact.owner}</span>
                </div>
              )}
              {!card.whoToContact.epcContractor && !card.whoToContact.operator && !card.whoToContact.owner && (
                <div className="flex gap-2">
                  <span className="text-fpso-dim flex-shrink-0">联系人:</span>
                  <span className="inline-flex items-center rounded bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-400 ring-1 ring-amber-400/20">
                    待补充
                  </span>
                </div>
              )}
              <div className="mt-2 rounded-md bg-fpso-orange/10 border border-fpso-orange/15 px-2.5 py-1.5">
                <p className="text-xs text-fpso-orange/90 font-medium leading-relaxed">
                  {card.whoToContact.recommendedRole}
                </p>
              </div>
            </div>
          </div>

          {/* when to contact — AI 时间窗优先，规则引擎兜底 */}
          {(() => {
            const useAi = analysis?.source === "ai" && !!analysis.procurement_window.range;
            return (
              <div>
                <SectionHeader source={useAi ? "ai" : undefined}>When to Contact · 何时联系</SectionHeader>
                <div className="rounded-md bg-fpso-blue/5 border border-fpso-blue/10 px-2.5 py-1.5">
                  {useAi ? (
                    <>
                      <p className="text-xs text-fpso-blue/90 font-semibold leading-relaxed">
                        采购时间窗 {analysis!.procurement_window.range}
                      </p>
                      {analysis!.procurement_window.reasoning && (
                        <p className="mt-1 text-[10px] leading-relaxed text-fpso-blue/70 italic">
                          {analysis!.procurement_window.reasoning}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-xs text-fpso-blue/90 leading-relaxed">
                      {card.whenToContact}
                    </p>
                  )}
                </div>
              </div>
            );
          })()}

          {/* next action — AI 结果优先，规则引擎兜底 */}
          {(() => {
            const useAi = analysis?.source === "ai" && !!analysis.action_suggestion;
            return (
              <div>
                <SectionHeader source={useAi ? "ai" : undefined}>Next Action · 下一步</SectionHeader>
                <div className="rounded-md bg-fpso-green/5 border border-fpso-green/10 px-2.5 py-1.5">
                  <p className="text-xs text-fpso-green font-semibold leading-relaxed">
                    {useAi ? analysis!.action_suggestion : card.nextAction}
                  </p>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* ---- footer ---- */}
      <div className="flex items-center justify-between px-5 py-3 border-t border-border bg-fpso-bg/30 text-[10px] text-fpso-dim">
        <div className="flex items-center gap-3">
          <span>{card.evidenceSummary}</span>
          {followUp && (
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border ${
              followUp.status === "contacted" ? "bg-fpso-blue/15 text-fpso-blue border-fpso-blue/30" :
              followUp.status === "valid" ? "bg-fpso-green/15 text-fpso-green border-fpso-green/30" :
              followUp.status === "inquiry" ? "bg-fpso-orange/15 text-fpso-orange border-fpso-orange/30" :
              followUp.status === "invalid" ? "bg-fpso-muted/15 text-fpso-muted border-fpso-muted/30" :
              "bg-fpso-green/15 text-fpso-green border-fpso-green/30"
            }`}>
              {FOLLOW_UP_STATUS_LABELS[followUp.status]}
            </span>
          )}
        </div>
        <span className="font-mono">
          {new Date(card.generatedAt).toLocaleString("zh-CN", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public BattleCard (wrapper w/ action buttons)
// ---------------------------------------------------------------------------

interface BattleCardWrapperProps {
  project: Project;
  baseUrl?: string;
  /** Timeline digest from the page — undefined shows 待补充 in the card. */
  timelineSummary?: string;
}

export default function BattleCardWrapper({ project, baseUrl, timelineSummary }: BattleCardWrapperProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [followUp, setFollowUp] = useState<FollowUp | null>(null);
  const [showOutreach, setShowOutreach] = useState(false);

  const { getFollowUp } = useFollowUp();

  const card = generateBattleCard(project, baseUrl);

  // AI 个性化分析（同飞书推送）— LLM 请求中显示加载态，返回后替换规则结果
  const { analysis, loading: analysisLoading } = usePushAnalysisState(project);

  // Fetch follow-up status on mount
  useEffect(() => {
    getFollowUp(project.name).then(setFollowUp);
  }, [project.name, getFollowUp]);

  const filename = `BattleCard_${project.name.replace(/[^a-zA-Z0-9一-鿿]/g, "_")}_${card.generatedAt.slice(0, 10)}.png`;

  const onCopyLink = useCallback(async () => {
    await copyLink(card.projectUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [card.projectUrl]);

  const onPrint = useCallback(() => {
    handlePrint();
  }, []);

  const onDownloadPng = useCallback(() => {
    if (cardRef.current) {
      downloadPng(cardRef.current, filename);
    }
  }, [filename]);

  return (
    <div className="space-y-3">
      {/* Battle card display */}
      <BattleCardView
        card={card}
        innerRef={cardRef}
        followUp={followUp}
        timelineSummary={timelineSummary}
        analysis={analysis}
        analysisLoading={analysisLoading}
      />

      {/* Action buttons */}
      <div className="flex items-center justify-center gap-3 pb-2 no-print">
        <button
          type="button"
          onClick={onCopyLink}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-fpso-card/40 px-3 py-1.5 text-xs font-medium text-fpso-fg hover:bg-fpso-blue/10 hover:text-fpso-blue hover:border-fpso-blue/30 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          {copied ? "Copied!" : "Copy Link"}
        </button>

        <button
          type="button"
          onClick={onPrint}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-fpso-card/40 px-3 py-1.5 text-xs font-medium text-fpso-fg hover:bg-fpso-blue/10 hover:text-fpso-blue hover:border-fpso-blue/30 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
          </svg>
          Print
        </button>

        <button
          type="button"
          onClick={onDownloadPng}
          className="inline-flex items-center gap-1.5 rounded-md border border-fpso-green/20 bg-fpso-green/5 px-3 py-1.5 text-xs font-medium text-fpso-green hover:bg-fpso-green/10 hover:border-fpso-green/30 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download PNG
        </button>

        <button
          type="button"
          onClick={() => setShowOutreach(true)}
          className="inline-flex items-center gap-1.5 rounded-md border border-fpso-orange/20 bg-fpso-orange/5 px-3 py-1.5 text-xs font-medium text-fpso-orange hover:bg-fpso-orange/10 hover:border-fpso-orange/30 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          生成开发信
        </button>
      </div>

      {/* 开发信弹窗 */}
      {showOutreach && (
        <OutreachModal project={project} onClose={() => setShowOutreach(false)} />
      )}

      {/* Print-only styles */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #ffffff !important; }
          .battle-card { box-shadow: none !important; border: 1px solid #e2e8f0 !important; }
        }
      `}</style>
    </div>
  );
}
