import { useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

/**
 * Optional-login guard for single actions.
 *
 * Anonymous visitors can browse everything. Actions that need a user
 * identity (CSV export, follow-up save, follow project, subscription
 * save) call `requireLogin()` first — it returns `false` and redirects
 * to /login (preserving the return path) when not authenticated.
 */
export function useRequireLogin() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const requireLogin = useCallback((): boolean => {
    if (isAuthenticated) return true;
    toast.error('Please log in with Feishu to use this feature');
    navigate('/login', { state: { from: location.pathname + location.search } });
    return false;
  }, [isAuthenticated, navigate, location.pathname, location.search]);

  return requireLogin;
}
