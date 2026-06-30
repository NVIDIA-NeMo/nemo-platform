// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ROUTES } from '@studio/constants/routes';
import { gateInferenceProviderRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const InferenceProvidersListRoute = lazy(() =>
  import('@studio/routes/InferenceProvidersListRoute').then((module) => ({
    default: module.InferenceProvidersListRoute,
  }))
);

export const inferenceProviderRoutes: RouteObject[] = gateInferenceProviderRoutes([
  {
    path: ROUTES.workspace.inferenceProviders,
    element: <InferenceProvidersListRoute />,
    errorElement: <ErrorPanel title="Inference Providers" />,
  },
]);
