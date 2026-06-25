// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { CODING_AGENT_STUDIO_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateCodingAgentStudioRoutes, gateDashboardRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

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
const ClaudeCodeChatRoute = lazy(() =>
  import('@studio/routes/agents/ClaudeCodeChatRoute').then((m) => ({
    default: m.ClaudeCodeChatRoute,
  }))
);

export const dashboardRoutes: RouteObject[] = gateDashboardRoutes([
  {
    path: ROUTES.workspace.dashboard,
    element: CODING_AGENT_STUDIO_ENABLED ? <DashboardLandingRoute /> : <WorkspaceDashboardRoute />,
    errorElement: <ErrorPanel title="Workspace" />,
  },
  ...gateCodingAgentStudioRoutes([
    {
      path: ROUTES.workspace.claudeCodeChat,
      element: <ClaudeCodeChatRoute />,
      errorElement: <ErrorPanel title="Claude Code" />,
    },
  ]),
]);
