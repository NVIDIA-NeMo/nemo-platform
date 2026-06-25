// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateMembersRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const WorkspaceMembersRoute = lazy(() =>
  import('@studio/routes/WorkspaceMembersRoute').then((module) => ({
    default: module.WorkspaceMembersRoute,
  }))
);

export const memberRoutes: RouteObject[] = gateMembersRoutes([
  {
    path: ROUTES.workspace.members,
    element: <WorkspaceMembersRoute />,
    errorElement: <ErrorPanel title="Members" />,
  },
]);
