import DashboardPage from './pages/DashboardPage';
import DatabasePage from './pages/DatabasePage';
import ReviewPage from './pages/ReviewPage';
import SettingsPage from './pages/SettingsPage';
import IndustryBreakdownPage from './pages/IndustryBreakdownPage';
import ProjectTimelinePage from './pages/ProjectTimelinePage';
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
    name: 'Dashboard',
    path: '/',
    element: <DashboardPage />,
    public: true,
  },
  {
    name: 'Database',
    path: '/database',
    element: <DatabasePage />,
    public: true,
  },
  {
    name: 'Review',
    path: '/review',
    element: <ReviewPage />,
    public: true,
  },
  {
    name: 'IndustryBreakdown',
    path: '/industry-breakdown',
    element: <IndustryBreakdownPage />,
    public: true,
  },
  {
    name: 'Settings',
    path: '/settings',
    element: <SettingsPage />,
    public: true,
  },
  {
    name: 'ProjectTimeline',
    path: '/project-timeline',
    element: <ProjectTimelinePage />,
    public: true,
  },
];
