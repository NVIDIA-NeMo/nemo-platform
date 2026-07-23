// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { OPTIMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateOptimizerRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const OptimizerRoute =
  OPTIMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/optimizer/OptimizerRoute').then((m) => ({
      default: m.OptimizerRoute,
    }))
  );

const OptimizerInsightRoute =
  OPTIMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/optimizer/OptimizerInsightRoute').then((m) => ({
      default: m.OptimizerInsightRoute,
    }))
  );

const OptimizerEvalAuthorRunRoute =
  OPTIMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/optimizer/OptimizerEvalAuthorRunRoute').then((m) => ({
      default: m.OptimizerEvalAuthorRunRoute,
    }))
  );

export const optimizerRoutes: RouteObject[] = gateOptimizerRoutes(
  OptimizerRoute && OptimizerInsightRoute && OptimizerEvalAuthorRunRoute
    ? [
        {
          path: ROUTES.workspace.optimizer,
          element: <OptimizerRoute />,
          errorElement: <ErrorPanel title="Insights" />,
        },
        {
          path: ROUTES.workspace.optimizerInsight,
          element: <OptimizerInsightRoute />,
          errorElement: <ErrorPanel title="Insight" />,
        },
        {
          path: ROUTES.workspace.optimizerEvalAuthorRun,
          element: <OptimizerEvalAuthorRunRoute />,
          errorElement: <ErrorPanel title="Eval Author run" />,
        },
      ]
    : []
);
