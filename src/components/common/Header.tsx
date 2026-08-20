import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Radar, FileText, History } from 'lucide-react';
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
  return `text-sm font-medium transition-colors ${isActive ? 'text-fpso-blue' : 'text-fpso-muted hover:text-fpso-blue/70'}`;
}

export default function Header({ rightContent }: { rightContent?: ReactNode }) {
  const { user, isAuthenticated, login, logout, loading } = useAuth();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-white/5 bg-fpso-bg/70 backdrop-blur-md">
      <div className="relative mx-auto flex h-16 max-w-7xl items-center px-6">
        {/* left: title */}
        <div className="z-10 flex-shrink-0">
          <span className="text-lg font-bold tracking-tight neon-glow md:text-xl">
            Business Opportunity Discovery
          </span>
        </div>

        {/* center: nav — absolutely positioned, always centered regardless of side content width */}
        {/* Database link intentionally removed from nav; /database route stays for internal use. */}
        <nav className="absolute left-1/2 -translate-x-1/2 z-10 hidden items-center gap-6 lg:flex">
          <NavLink to="/" end className={linkClass}>
            <span className="inline-flex items-center gap-1.5">
              <Radar className="h-4 w-4" />
              商机看板
            </span>
          </NavLink>
          <NavLink to="/battlecards" className={linkClass}>
            <span className="inline-flex items-center gap-1.5">
              <FileText className="h-4 w-4" />
              战报中心
            </span>
          </NavLink>
          <NavLink to="/project-timeline" className={linkClass}>
            <span className="inline-flex items-center gap-1.5">
              <History className="h-4 w-4" />
              项目时间线
            </span>
          </NavLink>
        </nav>

        {/* right: user controls + external rightContent */}
        <div className="z-10 ml-auto flex flex-shrink-0 items-center gap-4 overflow-hidden">
          {!loading && (
            isAuthenticated && user ? (
              /* Authenticated user: avatar dropdown */
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2 rounded-full hover:ring-2 hover:ring-fpso-blue/30 transition-all">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={user.avatar_url} alt={user.name} />
                      <AvatarFallback className="bg-fpso-blue/20 text-fpso-blue text-xs">
                        {user.name.slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden md:inline text-sm text-fpso-fg max-w-[120px] truncate">
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
              /* Unauthenticated: login button */
              <Button
                variant="outline"
                size="sm"
                onClick={login}
                className="border-fpso-blue/30 text-fpso-blue hover:bg-fpso-blue/10 text-xs"
              >
                Login with Feishu
              </Button>
            )
          )}
          {rightContent}
        </div>
      </div>
    </header>
  );
}
