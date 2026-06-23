// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateSecretsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const SecretsListRoute = lazy(() =>
  import('@studio/routes/SecretsListRoute').then((module) => ({ default: module.SecretsListRoute }))
);

export const secretsRoutes: RouteObject[] = gateSecretsRoutes([
  {
    path: ROUTES.workspace.secrets,
    element: <SecretsListRoute />,
    errorElement: <ErrorPanel title="Secrets" />,
  },
]);
