import DashboardPage from './pages/DashboardPage';
import DatabasePage from './pages/DatabasePage';
import ReviewPage from './pages/ReviewPage';
import SettingsPage from './pages/SettingsPage';
import IndustryBreakdownPage from './pages/IndustryBreakdownPage';
import ProjectTimelinePage from './pages/ProjectTimelinePage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import LoginPage from './pages/LoginPage';
import type { ReactNode } from 'react';

export interface RouteConfig {
  name: string;
  path: string;
  element: ReactNode;
  visible?: boolean;
  /** Accessible without login. Routes without this flag require authentication. Has no effect when RouteGuard is not in use. */
  public?: boolean;
}

export const routes: RouteConfig[] = [
  {
    name: 'Login',
    path: '/login',
    element: <LoginPage />,
    public: true,
  },
  {
    name: 'AuthCallback',
    path: '/auth/callback',
    element: <AuthCallbackPage />,
    public: true,
  },
  {
    name: 'Dashboard',
    path: '/',
    element: <DashboardPage />,
  },
  {
    name: 'Database',
    path: '/database',
    element: <DatabasePage />,
  },
  {
    name: 'Review',
    path: '/review',
    element: <ReviewPage />,
  },
  {
    name: 'IndustryBreakdown',
    path: '/industry-breakdown',
    element: <IndustryBreakdownPage />,
  },
  {
    name: 'Settings',
    path: '/settings',
    element: <SettingsPage />,
  },
  {
    name: 'ProjectTimeline',
    path: '/project-timeline',
    element: <ProjectTimelinePage />,
  },
];
