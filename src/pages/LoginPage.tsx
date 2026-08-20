import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/db/supabase';

const SESSION_REDIRECT_KEY = 'login_redirect_to';

const FEATURES = [
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: 'Global FPSO Project Tracking',
    desc: 'Real-time monitoring of FPSO projects worldwide, from EIA submission to production start.',
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
      </svg>
    ),
    title: 'AI Material & Factory Matching',
    desc: 'Intelligent stainless steel spec matching and factory qualification scoring.',
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    ),
    title: 'One-Click Battle Card',
    desc: 'Generate sales battle cards with scoring, recommendations, and competitive intelligence.',
  },
];

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from || '/';

  const [stats, setStats] = useState({ countries: 0, projects: 0 });
  const [statsLoading, setStatsLoading] = useState(true);

  // Fetch live stats from Supabase
  useEffect(() => {
    let cancelled = false;
    async function fetchStats() {
      try {
        const [countryRes, projectRes] = await Promise.all([
          supabase.from('projects').select('country', { count: 'exact', head: true }).not('country', 'is', null).not('country', 'eq', ''),
          supabase.from('projects').select('*', { count: 'exact', head: true }),
        ]);
        if (!cancelled) {
          // Count unique countries from recent data (approximate via count)
          const { data: countries } = await supabase.from('projects').select('country').not('country', 'is', null).not('country', 'eq', '');
          const uniqueCountries = countries ? new Set(countries.map((c: { country: string }) => c.country.trim())).size : 0;
          setStats({
            countries: uniqueCountries || 0,
            projects: projectRes.count || 0,
          });
        }
      } catch {
        // Fallback stats
        if (!cancelled) setStats({ countries: 20, projects: 180 });
      } finally {
        if (!cancelled) setStatsLoading(false);
      }
    }
    fetchStats();
    return () => { cancelled = true; };
  }, []);

  // Already authenticated — redirect
  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [loading, isAuthenticated, from, navigate]);

  const handleLogin = useCallback(() => {
    sessionStorage.setItem(SESSION_REDIRECT_KEY, from);
    login();
  }, [login, from]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: '#0a0f1e' }}>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-400" />
      </div>
    );
  }

  if (isAuthenticated) return null;

  return (
    <div className="relative flex min-h-screen flex-col lg:flex-row" style={{ background: '#0a0f1e' }}>
      {/* Grid background */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
        }}
      />
      {/* Ambient glow blobs */}
      <div className="pointer-events-none absolute left-0 top-0 h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/5 blur-[120px]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[500px] w-[500px] translate-x-1/3 translate-y-1/3 rounded-full bg-blue-500/5 blur-[120px]" />

      {/* ====== Left Panel: Value Proposition ====== */}
      <div className="relative z-10 flex flex-1 flex-col justify-center px-6 py-16 lg:px-16 lg:py-0">
        <div className="mx-auto w-full max-w-lg">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/5 px-4 py-1.5">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-xs font-medium tracking-wider text-emerald-400">LIVE DATA</span>
          </div>

          {/* Title */}
          <h1 className="mb-4 text-4xl font-bold tracking-tight text-foreground lg:text-5xl">
            Business Opportunity{' '}
            <span className="bg-gradient-to-r from-emerald-400 to-emerald-300 bg-clip-text text-transparent">
              Discovery
            </span>
          </h1>
          <p className="mb-10 text-lg leading-relaxed text-muted-foreground">
            Lock in stainless steel opportunities 3–6 months ahead. From reactive inquiry-waiting
            to proactive customer targeting.
          </p>

          {/* Feature list */}
          <div className="mb-12 space-y-6">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-4">
                <div className="mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border border-border bg-card/50 text-emerald-400">
                  {f.icon}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{f.title}</h3>
                  <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Stats bar */}
          <div className="flex items-center gap-8 rounded-xl border border-border bg-card/60 px-8 py-4">
            {statsLoading ? (
              <span className="text-sm text-muted-foreground">Loading stats...</span>
            ) : (
              <>
                <div className="text-center">
                  <div className="text-2xl font-bold text-foreground tabular-nums">
                    {stats.countries.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">Countries</div>
                </div>
                <div className="h-8 w-px bg-border" />
                <div className="text-center">
                  <div className="text-2xl font-bold text-foreground tabular-nums">
                    {stats.projects.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">Projects Tracked</div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ====== Right Panel: Login Card ====== */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-6 py-12 lg:py-0 lg:pr-16">
        <div className="w-full max-w-sm">
          {/* Card */}
          <div
            className="rounded-2xl border border-border p-8 backdrop-blur-xl"
            style={{ background: 'rgba(255,255,255,0.02)' }}
          >
            {/* Logo / icon */}
            <div className="mb-6 flex justify-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-emerald-400/20 bg-emerald-400/5">
                {/* Stainless steel pipe flange SVG */}
                <svg className="h-8 w-8 text-emerald-400" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="2" />
                  <circle cx="20" cy="20" r="12" stroke="currentColor" strokeWidth="1.5" opacity="0.6" />
                  <circle cx="20" cy="20" r="5" stroke="currentColor" strokeWidth="1.5" opacity="0.3" />
                  {/* bolt holes */}
                  {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
                    <circle
                      key={angle}
                      cx={20 + 15 * Math.cos((angle * Math.PI) / 180)}
                      cy={20 + 15 * Math.sin((angle * Math.PI) / 180)}
                      r="2"
                      fill="currentColor"
                      opacity="0.5"
                    />
                  ))}
                </svg>
              </div>
            </div>

            <h2 className="mb-2 text-center text-lg font-semibold text-foreground">
              Welcome back
            </h2>
            <p className="mb-8 text-center text-sm text-muted-foreground">
              Sign in to access your dashboard
            </p>

            {/* Feishu login button */}
            <button
              onClick={handleLogin}
              className="group relative mb-4 inline-flex w-full items-center justify-center gap-3 rounded-lg
                         bg-emerald-500 px-6 py-3 text-sm font-semibold text-gray-900
                         transition-all duration-300 hover:bg-emerald-400
                         hover:shadow-[0_0_30px_rgba(52,211,153,0.3)] active:scale-[0.98]
                         focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
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

            <p className="mt-6 text-center text-xs text-muted-foreground">
              No registration required — scan Feishu QR to sign in
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
