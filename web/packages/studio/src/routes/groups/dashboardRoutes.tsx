// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { COPILOT_STUDIO_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateCopilotStudioRoutes, gateDashboardRoutes } from '@studio/routes/utils';
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
const CopilotChatRoute = lazy(() =>
  import('@studio/routes/agents/CopilotChatRoute').then((m) => ({
    default: m.CopilotChatRoute,
  }))
);

export const dashboardRoutes: RouteObject[] = gateDashboardRoutes([
  {
    path: ROUTES.workspace.dashboard,
    element: COPILOT_STUDIO_ENABLED ? <DashboardLandingRoute /> : <WorkspaceDashboardRoute />,
    errorElement: <ErrorPanel title="Workspace" />,
  },
  ...gateCopilotStudioRoutes([
    {
      path: ROUTES.workspace.copilotChat,
      element: <CopilotChatRoute />,
      errorElement: <ErrorPanel title="NeMo Copilot" />,
    },
  ]),
]);
