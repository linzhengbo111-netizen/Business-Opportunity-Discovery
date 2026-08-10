import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { toast } from 'sonner';

/* ------------------------------------------------------------------ */
/*  types                                                              */
/* ------------------------------------------------------------------ */

export interface LarkUser {
  open_id: string;
  name: string;
  avatar_url: string;
  /** tenant_access_token is stored only for API calls; user-facing code should not rely on it */
}

interface AuthContextType {
  user: LarkUser | null;
  loading: boolean;
  login: () => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/* ------------------------------------------------------------------ */
/*  constants                                                          */
/* ------------------------------------------------------------------ */

const LARK_APP_ID = import.meta.env.VITE_LARK_APP_ID as string || '';
const LARK_REDIRECT_URI = `${window.location.origin}/auth/callback`;

const STORAGE_KEY = 'lark_user';

/* ------------------------------------------------------------------ */
/*  helpers                                                            */
/* ------------------------------------------------------------------ */

function loadUserFromStorage(): LarkUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.open_id && parsed.name) return parsed;
    return null;
  } catch {
    return null;
  }
}

function saveUserToStorage(user: LarkUser) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
}

function clearUserFromStorage() {
  localStorage.removeItem(STORAGE_KEY);
}

/**
 * Exchange Feishu authorization code for user_access_token and user info.
 * Called on the /auth/callback page.
 */
async function exchangeCodeForUser(code: string): Promise<LarkUser | null> {
  // Step 1: get user_access_token via OIDC endpoint
  const tokenResp = await fetch('https://open.feishu.cn/open-apis/authen/v1/oidc/access_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      code,
    }),
  });

  if (!tokenResp.ok) {
    console.error('Feishu token exchange failed:', await tokenResp.text());
    return null;
  }

  const tokenData = await tokenResp.json();
  if (tokenData.code !== 0) {
    console.error('Feishu token exchange error:', tokenData.msg);
    return null;
  }

  const userAccessToken = tokenData.data?.access_token;
  if (!userAccessToken) return null;

  // Step 2: get user info
  const userResp = await fetch('https://open.feishu.cn/open-apis/authen/v1/user_info', {
    headers: { Authorization: `Bearer ${userAccessToken}` },
  });

  if (!userResp.ok) {
    console.error('Feishu user info fetch failed:', await userResp.text());
    return null;
  }

  const userData = await userResp.json();
  if (userData.code !== 0) {
    console.error('Feishu user info error:', userData.msg);
    return null;
  }

  return {
    open_id: userData.data?.open_id || '',
    name: userData.data?.name || 'Unknown User',
    avatar_url: userData.data?.avatar_url || '',
  };
}

/* ------------------------------------------------------------------ */
/*  provider                                                           */
/* ------------------------------------------------------------------ */

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<LarkUser | null>(() => loadUserFromStorage());
  const [loading, setLoading] = useState(true);

  // Handle OAuth callback: check for ?code= in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (code) {
      // Clean URL immediately (remove code param)
      const newUrl = window.location.pathname + (state ? `?state=${state}` : '');
      window.history.replaceState({}, '', newUrl);

      exchangeCodeForUser(code).then((larkUser) => {
        if (larkUser) {
          setUser(larkUser);
          saveUserToStorage(larkUser);
          toast.success(`Welcome, ${larkUser.name}`);
        } else {
          toast.error('Feishu login failed. Please try again.');
        }
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(() => {
    if (!LARK_APP_ID) {
      toast.error('LARK_APP_ID is not configured. Set VITE_LARK_APP_ID in .env.');
      return;
    }

    // Generate random state for CSRF protection
    const state = crypto.randomUUID();
    sessionStorage.setItem('lark_oauth_state', state);

    const authUrl = new URL('https://open.feishu.cn/open-apis/authen/v1/authorize');
    authUrl.searchParams.set('app_id', LARK_APP_ID);
    authUrl.searchParams.set('redirect_uri', LARK_REDIRECT_URI);
    authUrl.searchParams.set('state', state);

    window.location.href = authUrl.toString();
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    clearUserFromStorage();
    toast.info('Logged out');
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        isAuthenticated: user !== null,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/*  hook                                                               */
/* ------------------------------------------------------------------ */

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
