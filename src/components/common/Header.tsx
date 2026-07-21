import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

function linkClass({ isActive }: { isActive: boolean }) {
  return `text-sm font-medium transition-colors ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-fpso-border bg-fpso-bg/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold tracking-tight neon-glow md:text-xl">
            Business Opportunity Discovery
          </span>
          <span className="hidden text-xs text-fpso-muted md:inline">
            Stainless Steel Opportunity Tracking in Global FPSO Projects
          </span>
        </div>

        <nav className="hidden items-center gap-8 md:flex">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/database" className={linkClass}>Database</NavLink>
          <NavLink to="/settings" className={linkClass}>Settings</NavLink>
        </nav>

        {rightContent ? (
          <div className="flex items-center gap-4">{rightContent}</div>
        ) : (
          <div className="flex items-center gap-4" />
        )}
      </div>
    </header>
  );
}
