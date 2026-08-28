/**
 * SidebarShell — 三页共享的左侧栏外壳
 * 视觉与商机看板 FilterSidebar 外壳完全一致：
 * fixed 定位、260px 展开 / 48px 折叠、同背景/边框/阴影、折叠态显示竖排标签窄条。
 * 商机看板 / 战报中心 / 项目时间线共用，保证三页切换时左侧栏不跳动。
 */

import type { ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";

export const SIDEBAR_EXPANDED = 260;
export const SIDEBAR_COLLAPSED = 48;
const NAV_HEIGHT = 64; // h-16

interface SidebarShellProps {
  collapsed: boolean;
  onToggle: () => void;
  /** 折叠态窄条显示的竖排文字标签（如 "Filters" / "Saved" / "Projects"）。 */
  collapsedLabel: string;
  /** 折叠态指示点（如「筛选激活」提示）。 */
  collapsedIndicator?: boolean;
  /** 指示点 title 文案。 */
  collapsedIndicatorTitle?: string;
  /** 展开态内容。 */
  children: ReactNode;
}

const SidebarShell = ({
  collapsed,
  onToggle,
  collapsedLabel,
  collapsedIndicator = false,
  collapsedIndicatorTitle = "Active",
  children,
}: SidebarShellProps) => (
  <>
    {/* Mobile backdrop overlay */}
    <div
      className={`md:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${
        collapsed ? "opacity-0 pointer-events-none" : "opacity-100"
      }`}
      onClick={onToggle}
      aria-hidden="true"
    />

    {/* Sidebar — fixed on desktop, overlay on mobile */}
    <aside
      className={`fixed top-16 left-0 z-40 border-r border-fpso-border bg-fpso-card/70 backdrop-blur-md transition-all duration-300 ease-in-out overflow-hidden
        max-md:shadow-2xl
        ${collapsed ? "max-md:-translate-x-full" : "max-md:translate-x-0"}
      `}
      style={{
        width: collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED,
        height: `calc(100vh - ${NAV_HEIGHT}px)`,
      }}
    >
      {/* Collapse toggle — always visible */}
      <button
        onClick={onToggle}
        className="absolute top-3 right-0 flex h-8 w-8 items-center justify-center rounded-l-md bg-fpso-card/80 text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/50 transition-colors border-y border-l border-border"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? (
          <PanelLeftOpen className="h-4 w-4" />
        ) : (
          <PanelLeftClose className="h-4 w-4" />
        )}
      </button>

      {/* Mobile close button */}
      <button
        onClick={onToggle}
        className="md:hidden absolute top-3 right-10 flex h-8 w-8 items-center justify-center rounded-md text-fpso-muted hover:text-fpso-fg hover:bg-fpso-border/30 transition-colors"
        title="Close sidebar"
      >
        <X className="h-4 w-4" />
      </button>

      {/* Collapsed state: icon column */}
      {collapsed && (
        <div className="flex flex-col items-center gap-4 pt-16">
          <span className="text-fpso-muted text-[10px] font-semibold uppercase tracking-widest writing-vertical">
            {collapsedLabel}
          </span>
          {collapsedIndicator && (
            <span
              className="inline-flex h-2 w-2 rounded-full bg-fpso-blue"
              title={collapsedIndicatorTitle}
            />
          )}
        </div>
      )}

      {/* Expanded content */}
      <div
        className="transition-opacity duration-200 overflow-y-auto h-full"
        style={{ opacity: collapsed ? 0 : 1, pointerEvents: collapsed ? "none" : "auto" }}
      >
        {children}
      </div>
    </aside>
  </>
);

export default SidebarShell;
