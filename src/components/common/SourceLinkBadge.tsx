import { sourceLinkKind } from "@/lib/source_link";

/**
 * Link-type badge: 原文 (specific article/document) · 数据文件 (dataset file) ·
 * 待补充 (empty source_url).
 */
export function SourceLinkBadge({ url, className = "" }: { url: string | null | undefined; className?: string }) {
  const kind = sourceLinkKind(url);
  if (kind === null) {
    return (
      <span className={`text-[10px] font-normal text-fpso-dim ${className}`}>
        待补充
      </span>
    );
  }
  return (
    <span
      className={`text-[10px] font-normal text-fpso-dim ${className}`}
      title={kind === "data_file" ? "链接指向官方数据集文件，非具体原文" : "链接指向具体原文"}
    >
      {kind === "data_file" ? "数据文件" : "原文"}
    </span>
  );
}
