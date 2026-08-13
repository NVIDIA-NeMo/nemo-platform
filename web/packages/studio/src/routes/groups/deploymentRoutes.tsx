// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { DEPLOYMENTS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateDeploymentsRoutes, getWorkspaceDeploymentsRoute } from '@studio/routes/utils';
import { Rocket } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

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

export const getDeploymentSideNavItems = (workspace: string) =>
  DEPLOYMENTS_ENABLED
    ? [
        {
          id: 'deployments',
          slotIcon: <Rocket className={iconColorClass} />,
          slotLabel: 'Deployments',
          href: getWorkspaceDeploymentsRoute(workspace),
        },
      ]
    : [];
