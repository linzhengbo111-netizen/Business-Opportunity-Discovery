import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

function linkClass({ isActive }: { isActive: boolean }) {
  return `text-sm font-medium transition-colors ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-fpso-border bg-fpso-bg/90 backdrop-blur">
      <div className="mx-auto grid h-16 max-w-7xl grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center px-6">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="truncate text-lg font-bold tracking-tight neon-glow md:text-xl">
            Business Opportunity Discovery
          </span>
        </div>

        <nav className="hidden items-center gap-8 md:flex">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/database" className={linkClass}>Database</NavLink>
          <NavLink to="/review" className={linkClass}>Review</NavLink>
          <NavLink to="/settings" className={linkClass}>Settings</NavLink>
        </nav>

        <div className="flex items-center justify-end gap-4 overflow-hidden">
          {rightContent}
        </div>
      </div>
    </header>
  );
}
