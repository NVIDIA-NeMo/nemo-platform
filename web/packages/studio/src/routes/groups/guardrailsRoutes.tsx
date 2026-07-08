// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateGuardrailsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const GuardrailsRoute = lazy(() =>
  import('@studio/routes/guardrails/GuardrailsRoute').then((m) => ({
    default: m.GuardrailsRoute,
  }))
);

const GuardrailDetailRoute = lazy(() =>
  import('@studio/routes/guardrails/GuardrailDetailRoute').then((m) => ({
    default: m.GuardrailDetailRoute,
  }))
);

export const guardrailsRoutes: RouteObject[] = gateGuardrailsRoutes([
  {
    path: ROUTES.workspace.guardrails,
    element: <GuardrailsRoute />,
    errorElement: <ErrorPanel title="Guardrails" />,
  },
  {
    path: ROUTES.workspace.guardrailDetail,
    element: <GuardrailDetailRoute />,
    errorElement: <ErrorPanel title="Guardrails" />,
  },
]);
