import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';

function linkClass({ isActive }: { isActive: boolean }) {
  return `text-xs md:text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  const { user, isAuthenticated, isGuest, login, logout, loading } = useAuth();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-white/5 bg-fpso-bg/70 backdrop-blur-md">
      {/*
        Three-column grid: left (title) | center (nav) | right (controls).
        Columns 1 and 3 get equal fractional space; column 2 is auto-width.
        This keeps the nav perfectly centered regardless of left/right content width,
        and guarantees everything stays on one line.
      */}
      <div className="mx-auto grid h-16 max-w-7xl grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 px-4 md:px-6">
        {/* left: title — truncates when space is tight */}
        <div className="min-w-0">
          <span className="text-sm md:text-lg font-bold tracking-tight neon-glow truncate block">
            Business Opportunity Discovery
          </span>
        </div>

        {/* center: nav links */}
        <nav className="hidden items-center gap-3 md:gap-5 md:flex">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/database" className={linkClass}>Database</NavLink>
          <NavLink to="/industry-breakdown" className={linkClass}>Illustration</NavLink>
        </nav>

        {/* right: user controls — pushed to end via flex justify-end */}
        <div className="flex items-center justify-end gap-2 md:gap-3 min-w-0">
          {!loading && (
            isGuest ? (
              <div className="flex items-center gap-1.5 md:gap-2 flex-nowrap">
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] md:text-xs font-medium text-amber-400 whitespace-nowrap flex-shrink-0">
                  <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-400" />
                  </span>
                  <span className="hidden sm:inline">Guest Mode</span>
                  <span className="sm:hidden">Guest</span>
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={login}
                  className="border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-[11px] md:text-xs h-7 px-2.5 md:h-8 md:px-3 whitespace-nowrap"
                >
                  Feishu Login
                </Button>
              </div>
            ) : isAuthenticated && user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-1.5 md:gap-2 rounded-full hover:ring-2 hover:ring-fpso-blue/30 transition-all flex-shrink-0 whitespace-nowrap">
                    <Avatar className="h-7 w-7 md:h-8 md:w-8 flex-shrink-0">
                      <AvatarImage src={user.avatar_url} alt={user.name} />
                      <AvatarFallback className="bg-fpso-blue/20 text-fpso-blue text-[10px] md:text-xs">
                        {user.name.slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden md:inline text-sm text-fpso-fg max-w-[100px] truncate">
                      {user.name}
                    </span>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-3 py-2 text-sm text-fpso-muted truncate">
                    {user.name}
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <NavLink to="/settings" className="cursor-pointer w-full">
                      Settings
                    </NavLink>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={logout}
                    className="cursor-pointer text-red-400 hover:text-red-300"
                  >
                    Log Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={login}
                className="border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-[11px] md:text-xs h-7 px-2.5 md:h-8 md:px-3 whitespace-nowrap"
              >
                Feishu Login
              </Button>
            )
          )}
          {rightContent}
        </div>
      </div>
    </header>
  );
}
