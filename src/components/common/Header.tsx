import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

function linkClass({ isActive }: { isActive: boolean }) {
  return `text-sm font-medium transition-colors ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-fpso-border bg-fpso-bg/90 backdrop-blur">
      <div className="relative mx-auto flex h-16 max-w-7xl items-center overflow-hidden px-6">
        {/* left: title */}
        <div className="z-10 flex-shrink-0">
          <span className="text-lg font-bold tracking-tight neon-glow md:text-xl">
            Business Opportunity Discovery
          </span>
        </div>

        {/* center: nav — absolutely positioned, always centered regardless of side content width */}
        <nav className="absolute left-1/2 -translate-x-1/2 z-10 hidden items-center gap-8 md:flex">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/database" className={linkClass}>Database</NavLink>
          <NavLink to="/settings" className={linkClass}>Settings</NavLink>
        </nav>

        {/* right: controls */}
        <div className="z-10 ml-auto flex flex-shrink-0 items-center gap-4 overflow-hidden">
          {rightContent}
        </div>
      </div>
    </header>
  );
}
