/**
 * Outreach Modal (S9) — 开发信生成弹窗
 * ====================================
 *
 * Generates a cold-outreach email draft via generate_outreach_message and
 * shows subject + body with copy / download actions. On failure shows
 * "信息不足，暂无法生成开发信". Shared by BattleCard and Dashboard.
 *
 * No email is ever sent — text only, for the user to review and send.
 */

import { useEffect, useState } from "react";
import type { Project } from "@/data/projects";
import { generate_outreach_message, type OutreachMessage } from "@/lib/ai_analyst";

const DISCLAIMER = "AI 生成草稿，请人工审核后发送";

interface OutreachModalProps {
  /** Project to generate the email for. null = modal closed. */
  project: Project | null;
  onClose: () => void;
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for older browsers / non-HTTPS
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

function downloadTxt(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export default function OutreachModal({ project, onClose }: OutreachModalProps) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<OutreachMessage | null>(null);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!project) {
      setMessage(null);
      setFailed(false);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setMessage(null);
    setFailed(false);
    generate_outreach_message(project).then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (result) setMessage(result);
      else setFailed(true);
    });
    return () => { cancelled = true; };
  }, [project]);

  if (!project) return null;

  const filename = `Outreach_${project.name.replace(/[^a-zA-Z0-9一-鿿]/g, "_")}.txt`;

  const onCopyBody = async () => {
    if (!message) return;
    await copyText(message.body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const onDownloadTxt = () => {
    if (!message) return;
    downloadTxt(
      filename,
      [`Subject: ${message.subject}`, "", message.body, "", `--- ${DISCLAIMER} ---`].join("\n"),
    );
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center p-4 pt-[8vh]"
      onClick={onClose}
    >
      {/* 遮罩层 */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />

      {/* 弹窗容器 */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative z-10 w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-fpso-border bg-white/95 backdrop-blur-md shadow-lift animate-fade-in"
      >
        {/* header */}
        <div className="flex items-center justify-between gap-3 border-b border-fpso-border px-5 py-4">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-fpso-fg truncate">开发信草稿 · Outreach Draft</h3>
            <p className="mt-0.5 text-xs text-fpso-dim truncate">{project.name}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-fpso-muted transition-colors hover:bg-fpso-bg/50 hover:text-fpso-fg"
            aria-label="Close outreach modal"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* body */}
        <div className="p-5">
          {loading && (
            <p className="text-xs text-fpso-dim animate-pulse">AI 正在生成开发信，请稍候…</p>
          )}

          {!loading && failed && (
            <p className="text-xs text-fpso-orange">信息不足，暂无法生成开发信</p>
          )}

          {!loading && message && (
            <div className="space-y-3">
              {/* Subject */}
              <div>
                <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-fpso-dim">
                  Subject · 主题
                </h4>
                <p className="rounded-md border border-fpso-border bg-fpso-bg/60 px-3 py-2 text-xs font-medium text-fpso-fg">
                  {message.subject}
                </p>
              </div>

              {/* Body */}
              <div>
                <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-fpso-dim">
                  Body · 正文
                </h4>
                <p className="whitespace-pre-wrap rounded-md border border-fpso-border bg-fpso-bg/60 px-3 py-2 text-xs leading-relaxed text-fpso-fg/90">
                  {message.body}
                </p>
              </div>

              {/* Disclaimer */}
              <p className="rounded-md border border-fpso-orange/20 bg-fpso-orange/10 px-3 py-2 text-[11px] font-medium text-fpso-orange">
                {DISCLAIMER}
              </p>

              {/* Actions */}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={onCopyBody}
                  className="inline-flex items-center gap-1.5 rounded-md border border-fpso-blue/20 bg-fpso-blue/5 px-3 py-1.5 text-xs font-medium text-fpso-blue hover:bg-fpso-blue/10 hover:border-fpso-blue/30 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3" />
                  </svg>
                  {copied ? "Copied!" : "复制正文"}
                </button>

                <button
                  type="button"
                  onClick={onDownloadTxt}
                  className="inline-flex items-center gap-1.5 rounded-md border border-fpso-green/20 bg-fpso-green/5 px-3 py-1.5 text-xs font-medium text-fpso-green hover:bg-fpso-green/10 hover:border-fpso-green/30 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  下载 .txt
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
