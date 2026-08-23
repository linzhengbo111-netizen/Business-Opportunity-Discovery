import { useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

const SESSION_REDIRECT_KEY = 'login_redirect_to';

/**
 * Optional-login guard for single actions.
 *
 * Anonymous visitors can browse everything. Actions that need a user
 * identity (CSV export, follow-up save, follow project, subscription
 * save) call `requireLogin()` first — when not authenticated it shows a
 * toast and kicks off the Feishu OAuth flow directly (no /login page);
 * AuthContext restores the current URL after the callback.
 */
export function useRequireLogin() {
  const { isAuthenticated, login } = useAuth();
  const location = useLocation();

  const requireLogin = useCallback((): boolean => {
    if (isAuthenticated) return true;
    toast.error('Please log in with Feishu to use this feature');
    sessionStorage.setItem(
      SESSION_REDIRECT_KEY,
      location.pathname + location.search,
    );
    login();
    return false;
  }, [isAuthenticated, login, location.pathname, location.search]);

  return requireLogin;
}
