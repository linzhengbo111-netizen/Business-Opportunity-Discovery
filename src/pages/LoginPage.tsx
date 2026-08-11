import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

const SESSION_REDIRECT_KEY = 'login_redirect_to';

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: string })?.from || '/';

  // Already authenticated — skip login page
  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [loading, isAuthenticated, from, navigate]);

  const handleLogin = () => {
    sessionStorage.setItem(SESSION_REDIRECT_KEY, from);
    login();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: '#0a0f1e' }}>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-400" />
      </div>
    );
  }

  if (isAuthenticated) return null;

  return (
    <div
      className="flex items-center justify-center min-h-screen px-4"
      style={{ background: '#0a0f1e' }}
    >
      <div className="text-center max-w-md w-full">
        {/* Terminal cursor decoration */}
        <div className="mb-6 flex justify-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/30 text-emerald-400 text-xs font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            AUTH REQUIRED
          </div>
        </div>

        {/* Title */}
        <h1
          className="text-3xl sm:text-4xl font-bold mb-3 font-mono tracking-tight"
          style={{ color: '#e2e8f0' }}
        >
          Business Opportunity
          <br />
          <span style={{ color: '#4ade80' }}>Discovery</span>
        </h1>

        <p className="text-slate-500 text-sm mb-10 font-mono">
          Sign in with Feishu to continue
        </p>

        {/* Feishu login button */}
        <button
          onClick={handleLogin}
          className="group relative inline-flex items-center justify-center gap-3 px-8 py-3.5 rounded-lg
                     bg-emerald-500 hover:bg-emerald-400 text-gray-900 font-semibold text-base
                     transition-all duration-200 hover:shadow-lg hover:shadow-emerald-500/25
                     active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
        >
          {/* Feishu icon (inline SVG) */}
          <svg
            className="w-5 h-5"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M17.5 3C19.985 3 22 5.015 22 7.5v9c0 2.485-2.015 4.5-4.5 4.5h-11C4.015 21 2 18.985 2 16.5v-9C2 5.015 4.015 3 6.5 3h11Z"
              fill="currentColor"
            />
            <path
              d="M6.75 8.25h3.75v3.75H6.75V8.25Zm6.75 0h3.75v3.75H13.5V8.25Zm-6 6.75h3.75v3.75H7.5v-3.75Z"
              fill="#0a0f1e"
            />
          </svg>
          Feishu Login
        </button>

        <p className="text-slate-600 text-xs mt-8 font-mono">
          powered by Feishu OIDC
        </p>
      </div>
    </div>
  );
}
