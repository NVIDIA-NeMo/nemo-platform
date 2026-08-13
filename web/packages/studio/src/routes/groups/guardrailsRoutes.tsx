// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { GUARDRAIL_CHECKS_DEFAULT_SUB_TAB } from '@studio/routes/guardrails/GuardrailChecksTab/constants';
import { gateGuardrailsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import { Navigate, type RouteObject } from 'react-router';

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

const GuardrailConfigTab = lazy(() =>
  import('@studio/routes/guardrails/GuardrailConfigTab').then((m) => ({
    default: m.GuardrailConfigTab,
  }))
);

const GuardrailChecksTab = lazy(() =>
  import('@studio/routes/guardrails/GuardrailChecksTab').then((m) => ({
    default: m.GuardrailChecksTab,
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
    children: [
      {
        index: true,
        element: <Navigate to="config" replace />,
      },
      {
        path: ROUTES.workspace.guardrailConfig,
        element: <GuardrailConfigTab />,
      },
      {
        path: ROUTES.workspace.guardrailChecks,
        element: <Navigate to={GUARDRAIL_CHECKS_DEFAULT_SUB_TAB} replace />,
      },
      {
        path: ROUTES.workspace.guardrailChecksSubTab,
        element: <GuardrailChecksTab />,
      },
    ],
  },
]);
