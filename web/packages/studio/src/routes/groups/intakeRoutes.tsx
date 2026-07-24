// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack } from '@nvidia/foundations-react-core';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { INTAKE_FILTER_ACTION_TARGET_ID } from '@studio/routes/IntakeLayout';
import { gateIntakeRoutes } from '@studio/routes/utils';
import { FC, lazy } from 'react';
import { Navigate, RouteObject } from 'react-router-dom';

const IntakeLayout = lazy(() =>
  import('@studio/routes/IntakeLayout').then((module) => ({ default: module.IntakeLayout }))
);
const IntakeTracesTableRoute = lazy(() =>
  import('@studio/components/IntakeLists/IntakeTracesTable').then(({ IntakeTracesTable }) => {
    const IntakeTracesTableRouteComponent: FC = () => (
      <Stack className="flex-1 min-h-0">
        <IntakeTracesTable slotEndPortalTargetId={INTAKE_FILTER_ACTION_TARGET_ID} />
      </Stack>
    );

    return { default: IntakeTracesTableRouteComponent };
  })
);
const IntakeSpansTableRoute = lazy(() =>
  import('@studio/components/IntakeLists/IntakeSpansTable').then(({ IntakeSpansTable }) => {
    const IntakeSpansTableRouteComponent: FC = () => (
      <Stack className="flex-1 min-h-0">
        <IntakeSpansTable slotEndPortalTargetId={INTAKE_FILTER_ACTION_TARGET_ID} />
      </Stack>
    );

    return { default: IntakeSpansTableRouteComponent };
  })
);
const IntakeSessionDetailRoute = lazy(() =>
  import('@studio/routes/IntakeSessionDetailRoute').then((module) => ({
    default: module.IntakeSessionDetailRoute,
  }))
);

export const intakeRoutes: RouteObject[] = gateIntakeRoutes([
  {
    path: ROUTES.workspace.intake,
    element: <IntakeLayout />,
    errorElement: <ErrorPanel title="Intake" />,
    children: [
      {
        index: true,
        element: <Navigate to="traces" replace />,
      },
      {
        path: ROUTES.workspace.intakeTraces,
        element: <IntakeTracesTableRoute />,
      },
      {
        path: ROUTES.workspace.intakeSpans,
        element: <IntakeSpansTableRoute />,
      },
    ],
  },
  {
    path: ROUTES.workspace.intakeSession,
    element: <IntakeSessionDetailRoute />,
    errorElement: <ErrorPanel title="Intake" />,
  },
]);
