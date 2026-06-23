// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateSettingsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const WorkspaceSettingsRoute = lazy(() =>
  import('@studio/routes/WorkspaceSettingsRoute').then((module) => ({
    default: module.WorkspaceSettingsRoute,
  }))
);

export const settingsRoutes: RouteObject[] = gateSettingsRoutes([
  {
    path: ROUTES.workspace.settings,
    element: <WorkspaceSettingsRoute />,
    errorElement: <ErrorPanel title="Settings" />,
  },
]);
