// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { GUARDRAILS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateGuardrailsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const GuardrailsRoute =
  GUARDRAILS_ENABLED &&
  lazy(() =>
    import('@studio/routes/guardrails/GuardrailsRoute').then((m) => ({
      default: m.GuardrailsRoute,
    }))
  );

export const guardrailsRoutes: RouteObject[] = gateGuardrailsRoutes(
  GuardrailsRoute
    ? {
        path: ROUTES.workspace.guardrails,
        element: <GuardrailsRoute />,
        errorElement: <ErrorPanel title="Guardrails" />,
      }
    : []
);
