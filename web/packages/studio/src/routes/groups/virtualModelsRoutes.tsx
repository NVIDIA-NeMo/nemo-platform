// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateGuardrailsRoutes } from '@studio/routes/utils';
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
    errorElement: <ErrorPanel title="Virtual Models" />,
  },
]);
