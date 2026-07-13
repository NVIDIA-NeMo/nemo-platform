// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { DATA_DESIGNER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateDataDesignerRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const DataDesignerJobListRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/DataDesignerJobListRoute').then((m) => ({
      default: m.DataDesignerJobListRoute,
    }))
  );
const DataDesignerJobDetailsRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/DataDesignerJobDetailsRoute').then((m) => ({
      default: m.DataDesignerJobDetailsRoute,
    }))
  );
const NewDataDesignerJobRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/NewDataDesignerJobRoute').then((m) => ({
      default: m.NewDataDesignerJobRoute,
    }))
  );
const DataDesignerJobBuildRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/DataDesignerJobBuildRoute').then((m) => ({
      default: m.DataDesignerJobBuildRoute,
    }))
  );
const LegacyNewDataDesignerJobRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/LegacyNewDataDesignerJobRoute').then((m) => ({
      default: m.LegacyNewDataDesignerJobRoute,
    }))
  );

export const dataDesignerRoutes: RouteObject[] = gateDataDesignerRoutes([
  {
    path: ROUTES.workspace.dataDesignerJobList,
    element: DataDesignerJobListRoute ? <DataDesignerJobListRoute /> : null,
    errorElement: <ErrorPanel title="Data Designer" />,
  },
  {
    path: ROUTES.workspace.dataDesignerJobDetails,
    element: DataDesignerJobDetailsRoute ? <DataDesignerJobDetailsRoute /> : null,
    errorElement: <ErrorPanel title="Data Designer" />,
  },
  {
    path: ROUTES.workspace.dataDesignerJobNew,
    element: NewDataDesignerJobRoute ? <NewDataDesignerJobRoute /> : null,
    errorElement: <ErrorPanel title="Data Designer" />,
  },
  {
    path: ROUTES.workspace.dataDesignerJobBuild,
    element: DataDesignerJobBuildRoute ? <DataDesignerJobBuildRoute /> : null,
    errorElement: <ErrorPanel title="Data Designer" />,
  },
  {
    path: ROUTES.workspace.dataDesignerJobNewLegacy,
    element: LegacyNewDataDesignerJobRoute ? <LegacyNewDataDesignerJobRoute /> : null,
    errorElement: <ErrorPanel title="Data Designer" />,
  },
]);
