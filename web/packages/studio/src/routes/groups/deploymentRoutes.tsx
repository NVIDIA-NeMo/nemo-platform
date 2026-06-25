// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { DEPLOYMENTS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateDeploymentsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const DeploymentsListRoute =
  DEPLOYMENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/DeploymentsListRoute').then((module) => ({
      default: module.DeploymentsListRoute,
    }))
  );

export const deploymentRoutes: RouteObject[] = gateDeploymentsRoutes([
  {
    path: ROUTES.workspace.deployments,
    element: DeploymentsListRoute ? <DeploymentsListRoute /> : null,
    errorElement: <ErrorPanel title="Deployments" />,
  },
  {
    path: ROUTES.workspace.deploymentsDeployment,
    element: DeploymentsListRoute ? <DeploymentsListRoute /> : null,
    errorElement: <ErrorPanel title="Deployments" />,
  },
]);
