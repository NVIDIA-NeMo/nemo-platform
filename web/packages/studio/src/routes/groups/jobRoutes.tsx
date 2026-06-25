// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateJobsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const JobsRoute = lazy(() =>
  import('@studio/routes/JobsRoute').then((module) => ({
    default: module.JobsRoute,
  }))
);
const JobDetailRoute = lazy(() =>
  import('@studio/routes/JobDetailRoute').then((module) => ({
    default: module.JobDetailRoute,
  }))
);

export const jobRoutes: RouteObject[] = gateJobsRoutes([
  {
    path: ROUTES.workspace.jobs,
    element: <JobsRoute />,
    errorElement: <ErrorPanel title="Jobs" />,
  },
  {
    path: ROUTES.workspace.jobDetail,
    element: <JobDetailRoute />,
    errorElement: <ErrorPanel title="Job Details" />,
  },
]);
