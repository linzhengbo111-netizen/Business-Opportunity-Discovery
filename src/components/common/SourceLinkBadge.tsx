import { sourceLinkKind } from "@/lib/source_link";

/**
 * Link-type badge: 原文 (specific article/document) · 数据文件 (dataset file) ·
 * 待补充 (empty source_url).
 */
export function SourceLinkBadge({ url, className = "" }: { url: string | null | undefined; className?: string }) {
  const kind = sourceLinkKind(url);
  if (kind === null) {
    return (
      <span
        className={`inline-flex items-center rounded bg-fpso-dim/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-dim ${className}`}
      >
        待补充
      </span>
    );
  }
  if (kind === "data_file") {
    return (
      <span
        className={`inline-flex items-center rounded bg-fpso-orange/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-orange/80 ring-1 ring-fpso-orange/10 ${className}`}
        title="链接指向官方数据集文件，非具体原文"
      >
        数据文件
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded bg-fpso-green/10 px-1.5 py-0.5 text-[10px] font-medium text-fpso-green ring-1 ring-fpso-green/10 ${className}`}
      title="链接指向具体原文"
    >
      原文
    </span>
  );
}
