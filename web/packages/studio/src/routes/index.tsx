// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTES } from '@studio/constants/routes';
import {
  agentRoutes,
  baseModelsRoutes,
  customizationRoutes,
  dashboardRoutes,
  dataDesignerRoutes,
  deploymentRoutes,
  evaluationRoutes,
  experimentRoutes,
  filesetRoutes,
  guardrailsRoutes,
  inferenceProviderRoutes,
  intakeRoutes,
  jobRoutes,
  memberRoutes,
  modelCompareRoutes,
  safeSynthesizerRoutes,
  secretsRoutes,
  settingsRoutes,
} from '@studio/routes/groups';
import { PageLayout } from '@studio/routes/PageLayout';
import { RootLayout } from '@studio/routes/RootLayout';
import { RootRedirect } from '@studio/routes/RootRedirect';
import { lazy, Suspense } from 'react';
import { Outlet } from 'react-router';
import type { RouteObject } from 'react-router-dom';

const NoMatchRoute = lazy(() =>
  import('@studio/routes/NoMatchRoute').then((module) => ({ default: module.NoMatchRoute }))
);
const AuthSuccessRoute = lazy(() =>
  import('@studio/routes/AuthSuccessRoute').then((m) => ({
    default: m.AuthSuccessRoute,
  }))
);
const WorkspaceIndexRoute = lazy(() =>
  import('@studio/routes/WorkspaceIndexRoute').then((module) => ({
    default: module.WorkspaceIndexRoute,
  }))
);
const WorkspaceSideNav = lazy(() =>
  import('@studio/routes/WorkspaceLayout/WorkspaceSideNav').then((module) => ({
    default: module.WorkspaceSideNav,
  }))
);

export const routes: RouteObject[] = [
  {
    path: '/health',
    element: <>OK</>,
  },
  {
    element: <RootLayout />,
    errorElement: <ErrorMessage height="100vh" />,
    children: [
      {
        path: ROUTES.auth.success,
        element: <AuthSuccessRoute />,
      },
      {
        element: <PageLayout />,
        children: [
          {
            path: '/',
            element: <RootRedirect />,
          },
          {
            path: '/workspaces',
            element: <RootRedirect />,
          },
          {
            path: '*',
            element: <NoMatchRoute />,
          },
        ],
      },
      {
        path: ROUTES.workspace.index,
        element: <PageLayout sideNav={(collapsed) => <WorkspaceSideNav collapsed={collapsed} />} />,
        children: [
          {
            path: ROUTES.workspace.index,
            element: <WorkspaceIndexRoute />,
          },
          {
            element: (
              // Suspense queries will show loader in panel area
              <Suspense fallback={<Loading description="Loading..." />}>
                <Outlet />
              </Suspense>
            ),
            errorElement: <ErrorPanel title="Entity Store" />,
            children: [
              ...dashboardRoutes,
              ...baseModelsRoutes,
              ...filesetRoutes,
              ...secretsRoutes,
              ...guardrailsRoutes,
              ...inferenceProviderRoutes,
              ...deploymentRoutes,
              ...evaluationRoutes,
              ...experimentRoutes,
              ...customizationRoutes,
              ...jobRoutes,
              ...intakeRoutes,
              ...safeSynthesizerRoutes,
              ...dataDesignerRoutes,
              ...agentRoutes,
              ...settingsRoutes,
              ...modelCompareRoutes,
              ...memberRoutes,
            ],
          },
        ],
      },
      {
        path: '*',
        element: <NoMatchRoute />,
      },
    ],
  },
];
