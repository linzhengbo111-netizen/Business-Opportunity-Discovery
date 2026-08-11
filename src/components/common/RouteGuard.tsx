import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { routes } from '@/routes';

interface RouteGuardProps {
  children: React.ReactNode;
}

// System-level public routes (no need to register in routes.tsx)
const SYSTEM_PUBLIC_ROUTES = ['/login', '/403', '/404'];

// Derived from routes.tsx
const routePublicPaths = routes.filter(r => r.public).map(r => r.path);
const routeGuestPaths = routes.filter(r => r.guestAccessible).map(r => r.path);

const PUBLIC_ROUTES = [...SYSTEM_PUBLIC_ROUTES, ...routePublicPaths];
const GUEST_ROUTES = [...PUBLIC_ROUTES, ...routeGuestPaths];

function matchRoute(path: string, patterns: string[]) {
  return patterns.some(pattern => {
    if (pattern.includes('*')) {
      const regex = new RegExp('^' + pattern.replace('*', '.*') + '$');
      return regex.test(path);
    }
    return path === pattern;
  });
}

export function RouteGuard({ children }: RouteGuardProps) {
  const { user, loading, isGuest } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (loading) return;

    const isPublic = matchRoute(location.pathname, PUBLIC_ROUTES);
    const isGuestAccessible = matchRoute(location.pathname, GUEST_ROUTES);

    // Unauthenticated: only public routes
    if (!user && !isPublic) {
      navigate('/login', { state: { from: location.pathname }, replace: true });
      return;
    }

    // Guest: public + guestAccessible routes only
    if (user && isGuest && !isGuestAccessible) {
      navigate('/', { replace: true });
    }
  }, [user, loading, location.pathname, navigate, isGuest]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return <>{children}</>;
}
