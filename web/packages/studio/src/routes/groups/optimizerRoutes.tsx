// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { OPTIMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateOptimizerRoutes, getOptimizerRoute } from '@studio/routes/utils';
import { Lightbulb } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

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

export const optimizerRoutes: RouteObject[] = gateOptimizerRoutes(
  OptimizerRoute && OptimizerInsightRoute
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
      ]
    : []
);

export const getOptimizerSideNavItems = (workspace: string) =>
  OPTIMIZER_ENABLED
    ? [
        {
          id: 'optimizer',
          slotIcon: <Lightbulb className={iconColorClass} />,
          slotLabel: 'Insights',
          href: getOptimizerRoute(workspace),
        },
      ]
    : [];
