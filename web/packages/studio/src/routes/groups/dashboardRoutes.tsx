// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { ASSISTANT_STUDIO_ENABLED, DASHBOARD_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import {
  gateAssistantStudioRoutes,
  gateDashboardRoutes,
  getWorkspaceDashboardRoute,
} from '@studio/routes/utils';
import { LayoutDashboard } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

const DashboardLandingRoute = lazy(() =>
  import('@studio/routes/DashboardLandingRoute').then((module) => ({
    default: module.DashboardLandingRoute,
  }))
);
const WorkspaceDashboardRoute = lazy(() =>
  import('@studio/routes/WorkspaceDashboardRoute').then((module) => ({
    default: module.WorkspaceDashboardRoute,
  }))
);
const AssistantChatRoute = lazy(() =>
  import('@studio/routes/agents/AssistantChatRoute').then((module) => ({
    default: module.AssistantChatRoute,
  }))
);

export const dashboardRoutes: RouteObject[] = gateDashboardRoutes([
  {
    path: ROUTES.workspace.dashboard,
    element: ASSISTANT_STUDIO_ENABLED ? <DashboardLandingRoute /> : <WorkspaceDashboardRoute />,
    errorElement: <ErrorPanel title="Workspace" />,
  },
  ...gateAssistantStudioRoutes([
    {
      path: ROUTES.workspace.assistantChat,
      element: <AssistantChatRoute />,
      errorElement: <ErrorPanel title="NeMo Assistant" />,
    },
  ]),
]);

export const getDashboardSideNavItems = (workspace: string) =>
  DASHBOARD_ENABLED || ASSISTANT_STUDIO_ENABLED
    ? [
        {
          id: 'dashboard',
          slotIcon: <LayoutDashboard className={iconColorClass} />,
          slotLabel: 'Dashboard',
          href: getWorkspaceDashboardRoute(workspace),
        },
      ]
    : [];
