// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { MODEL_COMPARE_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateModelCompareRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const ModelCompareRoute =
  MODEL_COMPARE_ENABLED &&
  lazy(() =>
    import('@studio/routes/ModelCompareRoute').then((module) => ({
      default: module.ModelCompareRoute,
    }))
  );

export const modelCompareRoutes: RouteObject[] = gateModelCompareRoutes([
  {
    path: ROUTES.workspace.modelCompare,
    element: ModelCompareRoute ? <ModelCompareRoute /> : null,
    errorElement: <ErrorPanel title="Chat" />,
  },
]);
