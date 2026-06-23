// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateCustomizationRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const PromptTuningFormRoute = lazy(() =>
  import('@studio/routes/PromptTuningFormRoute/index').then((module) => ({
    default: module.PromptTuningFormRoute,
  }))
);
const CustomizationJobListRoute = lazy(() =>
  import('@studio/routes/CustomizationJobListRoute').then((module) => ({
    default: module.CustomizationJobListRoute,
  }))
);
const CustomizationJobDetailsRoute = lazy(() =>
  import('@studio/routes/CustomizationJobDetailsRoute').then((module) => ({
    default: module.CustomizationJobDetailsRoute,
  }))
);
const NewCustomizationRoute = lazy(() =>
  import('@studio/routes/NewCustomizationRoute').then((module) => ({
    default: module.NewCustomizationRoute,
  }))
);

export const customizationRoutes: RouteObject[] = gateCustomizationRoutes([
  {
    path: ROUTES.workspace.promptTuningForm,
    element: <PromptTuningFormRoute />,
    errorElement: <ErrorPanel title="Customizer" />,
  },
  {
    path: ROUTES.workspace.customizationJobList,
    element: <CustomizationJobListRoute />,
    errorElement: <ErrorPanel title="Customizer" />,
  },
  {
    path: ROUTES.workspace.customizationJobDetails,
    element: <CustomizationJobDetailsRoute />,
    errorElement: <ErrorPanel title="Customizer" />,
  },
  {
    path: ROUTES.workspace.newCustomizationJob,
    element: <NewCustomizationRoute />,
    errorElement: <ErrorPanel title="Customizer" />,
  },
]);
