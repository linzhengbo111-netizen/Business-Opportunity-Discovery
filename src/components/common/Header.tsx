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
  return `text-xs font-medium transition-colors whitespace-nowrap ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  const { user, isAuthenticated, isGuest, login, logout, loading } = useAuth();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-white/5 bg-fpso-bg/70 backdrop-blur-md">
      {/* Single-line flex bar: locked height, no wrap, no overflow */}
      <div className="mx-auto flex h-12 max-w-7xl flex-nowrap items-center gap-2 overflow-hidden whitespace-nowrap px-3 md:px-6">
        {/* Left: title — fixed small size, truncated */}
        <span className="flex-shrink-0 text-sm font-bold tracking-tight neon-glow truncate max-w-[160px] sm:max-w-[200px]">
          Business Opportunity Discovery
        </span>

        {/* Center spacer — pushes right content to the end */}
        <div className="flex-1 min-w-[8px]" />

        {/* Nav links — hidden below lg (1024px) */}
        <nav className="hidden lg:flex flex-shrink-0 items-center gap-4">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/database" className={linkClass}>Database</NavLink>
          <NavLink to="/industry-breakdown" className={linkClass}>Illustration</NavLink>
        </nav>

        {/* Right: user controls */}
        <div className="flex flex-shrink-0 items-center gap-2">
          {!loading && (
            isGuest ? (
              <>
                <span className="inline-flex flex-shrink-0 items-center gap-1 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-400">
                  <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400" />
                  <span className="hidden sm:inline">Guest</span>
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={login}
                  className="flex-shrink-0 border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-[11px] h-7 px-2"
                >
                  Login
                </Button>
              </>
            ) : isAuthenticated && user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex flex-shrink-0 items-center gap-1.5 rounded-full hover:ring-2 hover:ring-fpso-blue/30 transition-all">
                    <Avatar className="h-6 w-6 flex-shrink-0">
                      <AvatarImage src={user.avatar_url} alt={user.name} />
                      <AvatarFallback className="bg-fpso-blue/20 text-fpso-blue text-[10px]">
                        {user.name.slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden lg:inline text-xs text-fpso-fg max-w-[80px] truncate">
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
                className="flex-shrink-0 border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-[11px] h-7 px-2"
              >
                Login
              </Button>
            )
          )}
          {rightContent}
        </div>
      </div>
    </header>
  );
}
