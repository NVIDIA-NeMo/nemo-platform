// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateExperimentRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const ExperimentRoute = lazy(() =>
  import('@studio/routes/ExperimentRoute').then((module) => ({
    default: module.ExperimentRoute,
  }))
);
const ExperimentGroupDetailRoute = lazy(() =>
  import('@studio/routes/ExperimentGroupDetailRoute').then((module) => ({
    default: module.ExperimentGroupDetailRoute,
  }))
);
const EvaluationDetailRoute = lazy(() =>
  import('@studio/routes/EvaluationDetailRoute').then((module) => ({
    default: module.EvaluationDetailRoute,
  }))
);
const EvaluationTraceDetailRoute = lazy(() =>
  import('@studio/routes/EvaluationTraceDetailRoute').then((module) => ({
    default: module.EvaluationTraceDetailRoute,
  }))
);

export const experimentRoutes: RouteObject[] = gateExperimentRoutes([
  {
    path: ROUTES.workspace.experiment,
    element: <ExperimentRoute />,
    errorElement: <ErrorPanel title="Experiment Groups" />,
  },
  {
    path: ROUTES.workspace.experimentGroupDetail,
    element: <ExperimentGroupDetailRoute />,
    errorElement: <ErrorPanel title="Experiment Group" />,
  },
  {
    path: ROUTES.workspace.evaluationDetail,
    element: <EvaluationDetailRoute />,
    errorElement: <ErrorPanel title="Evaluation" />,
  },
  {
    path: ROUTES.workspace.evaluationTraceDetail,
    element: <EvaluationTraceDetailRoute />,
    errorElement: <ErrorPanel title="Trace" />,
  },
]);
