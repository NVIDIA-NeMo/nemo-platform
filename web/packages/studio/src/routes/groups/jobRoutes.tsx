// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { JOBS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateJobsRoutes, getWorkspaceJobsRoute } from '@studio/routes/utils';
import { ListChecks } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

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

export const getJobSideNavItems = (workspace: string) =>
  JOBS_ENABLED
    ? [
        {
          id: 'jobs',
          slotIcon: <ListChecks className={iconColorClass} />,
          slotLabel: 'Jobs',
          href: getWorkspaceJobsRoute(workspace),
        },
      ]
    : [];
