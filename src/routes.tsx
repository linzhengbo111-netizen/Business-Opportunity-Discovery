import DashboardPage from './pages/DashboardPage';
import DatabasePage from './pages/DatabasePage';
import BattleCardsPage from './pages/BattleCardsPage';
import ReviewPage from './pages/ReviewPage';
import SettingsPage from './pages/SettingsPage';
// IndustryBreakdownPage intentionally kept on disk — route removed, easy to restore later.
import ProjectTimelinePage from './pages/ProjectTimelinePage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import type { ReactNode } from 'react';

export interface RouteConfig {
  name: string;
  path: string;
  element: ReactNode;
  visible?: boolean;
  /** Accessible without login. Routes without this flag require authentication. */
  public?: boolean;
}

export const routes: RouteConfig[] = [
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
    name: 'BattleCards',
    path: '/battlecards',
    element: <BattleCardsPage />,
  },
  {
    name: 'Review',
    path: '/review',
    element: <ReviewPage />,
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
