// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { gateBaseModelsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const WorkspaceBaseModelsRoute = lazy(() =>
  import('@studio/routes/WorkspaceBaseModelsRoute').then((module) => ({
    default: module.WorkspaceBaseModelsRoute,
  }))
);

export const baseModelsRoutes: RouteObject[] = gateBaseModelsRoutes([
  {
    path: ROUTES.workspace.baseModels,
    element: <WorkspaceBaseModelsRoute />,
  },
  {
    path: ROUTES.workspace.baseModelsModel,
    element: <WorkspaceBaseModelsRoute />,
  },
]);
