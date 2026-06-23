// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateDatasetsRoutes, gateFilesetDetailsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const FilesetNewRoute = lazy(() =>
  import('@studio/routes/FilesetNewRoute').then((module) => ({ default: module.FilesetNewRoute }))
);
// Fileset details and file routes are not separate routes
// Both panels are rendered directly in FilesetListRoute
// Route paths are kept for URL matching only
const FilesetListRoute = lazy(() =>
  import('@studio/routes/FilesetListRoute').then((module) => ({ default: module.FilesetListRoute }))
);
const FilesetDetailRoute = lazy(() =>
  import('@studio/routes/FilesetDetailRoute').then((module) => ({
    default: module.FilesetDetailRoute,
  }))
);

export const filesetRoutes: RouteObject[] = gateDatasetsRoutes([
  {
    path: ROUTES.workspace.filesets,
    element: <FilesetListRoute />,
    errorElement: <ErrorPanel title="Filesets" />,
    children: [
      {
        path: ROUTES.workspace.filesetNew,
        element: <FilesetNewRoute />,
      },
      {
        path: ROUTES.workspace.filesetDetails,
        element: <></>, // Just for URL matching - panel rendered in FilesetListRoute
      },
      {
        path: ROUTES.workspace.filesetFile,
        element: <></>, // Just for URL matching - panel rendered in FilesetListRoute
      },
    ],
  },
  ...gateFilesetDetailsRoutes([
    {
      path: ROUTES.workspace.filesetDetail,
      element: <FilesetDetailRoute />,
      errorElement: <ErrorPanel title="Fileset" />,
    },
  ]),
]);
