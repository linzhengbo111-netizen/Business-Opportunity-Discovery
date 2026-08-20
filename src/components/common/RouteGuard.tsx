import { useAuth } from '@/contexts/AuthContext';

interface RouteGuardProps {
  children: React.ReactNode;
}

/**
 * Optional-login mode: all routes are browsable without authentication.
 * This guard only waits for the auth state to resolve from storage so
 * components (Header login button, gated actions) render with the
 * correct user state — it never redirects unauthenticated visitors.
 */
export function RouteGuard({ children }: RouteGuardProps) {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return <>{children}</>;
}
