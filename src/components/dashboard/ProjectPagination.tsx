/**
 * 项目列表分页控件 — 深色/浅色数据终端风格。
 * 小号圆角边框按钮；当前页 fpso-blue 实色高亮；
 * 页码带省略号窗口（首/尾 + 当前页 ±1），55 页也不会溢出。
 */

interface ProjectPaginationProps {
  page: number;
  totalPages: number;
  /** 当前页在完整有序列表中的起止位置（含置顶项目偏移），如 24-43。 */
  rangeStart: number;
  rangeEnd: number;
  /** 完整列表总数（含置顶项目）。 */
  totalCount: number;
  onPageChange: (page: number) => void;
}

type PageItem = number | "ellipsis-left" | "ellipsis-right";

/** 生成页码窗口：总数 ≤ 7 全列；否则 1 / … / page±1 / … / last。 */
function buildPageItems(page: number, totalPages: number): PageItem[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const items: PageItem[] = [1];
  const lo = Math.max(2, page - 1);
  const hi = Math.min(totalPages - 1, page + 1);
  if (lo > 2) items.push("ellipsis-left");
  for (let i = lo; i <= hi; i++) items.push(i);
  if (hi < totalPages - 1) items.push("ellipsis-right");
  items.push(totalPages);
  return items;
}

const BTN_BASE =
  "inline-flex h-7 min-w-7 items-center justify-center rounded-md border px-1.5 font-mono text-xs tabular-nums transition-colors duration-150";
const BTN_IDLE =
  "border-fpso-border bg-fpso-card text-fpso-muted hover:border-fpso-blue/50 hover:text-fpso-blue";
const BTN_CURRENT = "border-fpso-blue bg-fpso-blue text-white";

export default function ProjectPagination({
  page,
  totalPages,
  rangeStart,
  rangeEnd,
  totalCount,
  onPageChange,
}: ProjectPaginationProps) {
  if (totalCount === 0) return null;
  const items = buildPageItems(page, totalPages);
  const atFirst = page <= 1;
  const atLast = page >= totalPages;

  return (
    <div className="mt-4 flex flex-col items-center justify-between gap-3 border-t border-fpso-border pt-4 sm:flex-row">
      <span className="font-mono text-xs tabular-nums text-fpso-muted">
        显示 {rangeStart}-{rangeEnd} 条，共 {totalCount} 条
      </span>

      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <button
          type="button"
          disabled={atFirst}
          onClick={() => onPageChange(page - 1)}
          aria-label="上一页"
          className={`${BTN_BASE} ${BTN_IDLE} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          上一页
        </button>

        {items.map((item) =>
          item === "ellipsis-left" || item === "ellipsis-right" ? (
            <span
              key={item}
              className="inline-flex h-7 items-center justify-center px-0.5 font-mono text-xs text-fpso-dim"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onPageChange(item)}
              aria-label={`第 ${item} 页`}
              aria-current={item === page ? "page" : undefined}
              className={`${BTN_BASE} ${item === page ? BTN_CURRENT : BTN_IDLE}`}
            >
              {item}
            </button>
          ),
        )}

        <button
          type="button"
          disabled={atLast}
          onClick={() => onPageChange(page + 1)}
          aria-label="下一页"
          className={`${BTN_BASE} ${BTN_IDLE} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          下一页
        </button>

        <span className="ml-1 font-mono text-xs tabular-nums text-fpso-dim">
          第 {page} / {totalPages} 页
        </span>
      </div>
    </div>
  );
}
