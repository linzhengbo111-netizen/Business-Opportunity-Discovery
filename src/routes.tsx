import DashboardPage from './pages/DashboardPage';
import DatabasePage from './pages/DatabasePage';
import SettingsPage from './pages/SettingsPage';
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
    name: 'Settings',
    path: '/settings',
    element: <SettingsPage />,
    public: true,
  },
];
