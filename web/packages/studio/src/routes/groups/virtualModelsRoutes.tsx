// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RouteErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { GUARDRAILS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateGuardrailsRoutes, getWorkspaceVirtualModelsRoute } from '@studio/routes/utils';
import { Waypoints } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

const VirtualModelsListRoute = lazy(() =>
  import('@studio/routes/VirtualModelsListRoute').then((module) => ({
    default: module.VirtualModelsListRoute,
  }))
);

export const virtualModelsRoutes: RouteObject[] = gateGuardrailsRoutes([
  {
    path: ROUTES.workspace.virtualModels,
    element: <VirtualModelsListRoute />,
    errorElement: <RouteErrorPanel title="Virtual Models" />,
  },
]);

export const getVirtualModelsSideNavItems = (workspace: string) =>
  GUARDRAILS_ENABLED
    ? [
        {
          id: 'virtual-models',
          slotIcon: <Waypoints className={iconColorClass} />,
          slotLabel: 'Virtual Models',
          href: getWorkspaceVirtualModelsRoute(workspace),
        },
      ]
    : [];
