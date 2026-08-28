/**
 * PageHeader — 共享页面标题区
 * 统一商机看板 / 战报中心 / 项目时间线三个页面的标题布局：
 * 左侧 h1 + 副标题，右侧可选操作区，标题区下方统一 mb-6 间距。
 */

import type { ReactNode } from "react";

interface PageHeaderProps {
  /** 主标题 — 接受 ReactNode，支持渐变 span 等内联样式。 */
  title: ReactNode;
  /** 可选副标题，显示在标题下方。 */
  subtitle?: ReactNode;
  /** 可选右侧操作区（按钮 / 状态文字）。 */
  actions?: ReactNode;
}

const PageHeader = ({ title, subtitle, actions }: PageHeaderProps) => (
  <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
    <div className="min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg">{title}</h1>
      {subtitle && <p className="mt-1 text-xs text-fpso-muted">{subtitle}</p>}
    </div>
    {actions && (
      <div className="flex flex-shrink-0 flex-wrap items-center gap-3">{actions}</div>
    )}
  </header>
);

export default PageHeader;
