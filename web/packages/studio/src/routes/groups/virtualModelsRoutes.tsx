// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const VirtualModelsListRoute = lazy(() =>
  import('@studio/routes/VirtualModelsListRoute').then((module) => ({
    default: module.VirtualModelsListRoute,
  }))
);

export const virtualModelsRoutes: RouteObject[] = [
  {
    path: ROUTES.workspace.virtualModels,
    element: <VirtualModelsListRoute />,
    errorElement: <ErrorPanel title="Virtual Models" />,
  },
];
