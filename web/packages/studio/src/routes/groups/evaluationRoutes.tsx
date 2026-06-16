// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateEvaluationBenchmarksRoutes, gateEvaluationRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import { Navigate, RouteObject } from 'react-router-dom';

const EvaluationLayout = lazy(() =>
  import('@studio/routes/evaluation/EvaluationLayout').then((module) => ({
    default: module.EvaluationLayout,
  }))
);
const EvaluationResultsLayout = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultsLayout').then((module) => ({
    default: module.EvaluationResultsLayout,
  }))
);
const EvaluationResultsRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultsRoute').then((module) => ({
    default: module.EvaluationResultsRoute,
  }))
);
const EvaluationResultDetailsRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultDetailsRoute').then((module) => ({
    default: module.EvaluationResultDetailsRoute,
  }))
);

export const evaluationRoutes: RouteObject[] = gateEvaluationRoutes([
  {
    path: ROUTES.workspace.evaluation,
    element: <EvaluationLayout />,
    errorElement: <ErrorPanel title="Evaluator" />,
    children: [
      {
        index: true,
        element: <Navigate to="results" replace />,
      },
      ...gateEvaluationBenchmarksRoutes([]),
    ],
  },
  {
    path: ROUTES.workspace.evaluationResultDetails,
    element: <EvaluationResultDetailsRoute />,
    errorElement: <ErrorPanel title="Evaluator" />,
  },
  {
    path: ROUTES.workspace.evaluationResults,
    element: <EvaluationResultsLayout />,
    errorElement: <ErrorPanel title="Evaluator" />,
    children: [
      {
        index: true,
        element: <EvaluationResultsRoute />,
      },
    ],
  },
]);
