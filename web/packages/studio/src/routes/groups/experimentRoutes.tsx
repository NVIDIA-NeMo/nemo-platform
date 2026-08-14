// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RouteErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { EXPERIMENT_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateExperimentRoutes, getExperimentRoute } from '@studio/routes/utils';
import { FlaskConical } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

const ExperimentRoute = lazy(() =>
  import('@studio/routes/ExperimentRoute').then((module) => ({
    default: module.ExperimentRoute,
  }))
);
const ExperimentDetailRoute = lazy(() =>
  import('@studio/routes/ExperimentDetailRoute').then((module) => ({
    default: module.ExperimentDetailRoute,
  }))
);
const EvaluationDetailRoute = lazy(() =>
  import('@studio/routes/EvaluationDetailRoute').then((module) => ({
    default: module.EvaluationDetailRoute,
  }))
);
const EvaluationSessionDetailRoute = lazy(() =>
  import('@studio/routes/EvaluationSessionDetailRoute').then((module) => ({
    default: module.EvaluationSessionDetailRoute,
  }))
);

export const experimentRoutes: RouteObject[] = gateExperimentRoutes([
  {
    path: ROUTES.workspace.experiment,
    element: <ExperimentRoute />,
    errorElement: <RouteErrorPanel title="Experiments" />,
  },
  {
    path: ROUTES.workspace.evaluationSessionDetail,
    element: <EvaluationSessionDetailRoute />,
    errorElement: <RouteErrorPanel title="Session" />,
  },
  {
    path: ROUTES.workspace.experimentDetail,
    element: <ExperimentDetailRoute />,
    errorElement: <RouteErrorPanel title="Experiment" />,
  },
  {
    path: ROUTES.workspace.evaluationDetail,
    element: <EvaluationDetailRoute />,
    errorElement: <RouteErrorPanel title="Evaluation" />,
  },
]);

export const getExperimentSideNavItems = (workspace: string) =>
  EXPERIMENT_ENABLED
    ? [
        {
          id: 'experiment',
          slotIcon: <FlaskConical className={iconColorClass} />,
          slotLabel: 'Experiments',
          href: getExperimentRoute(workspace),
        },
      ]
    : [];
