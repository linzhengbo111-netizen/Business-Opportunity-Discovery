/**
 * Classify a source_url for the link-type badge shown next to source links.
 * - data_file: URL points at a dataset/data file (XLSX/PDF/DOC/CSV/ZIP download),
 *   not a specific article or document page.
 * - article:   any other reachable URL — treated as a specific 原文.
 * - null:      empty source_url — frontend shows 待补充.
 */
export type SourceLinkKind = "article" | "data_file";

const FILE_EXTS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip"];

export function sourceLinkKind(url: string | null | undefined): SourceLinkKind | null {
  const u = (url ?? "").trim();
  if (!u) return null;
  try {
    const path = new URL(u).pathname.toLowerCase();
    if (FILE_EXTS.some((ext) => path.endsWith(ext))) return "data_file";
    return "article";
  } catch {
    return "article";
  }
}
