// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { PROMPTS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gatePromptsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const PromptsListRoute =
  PROMPTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/PromptsListRoute').then((module) => ({
      default: module.PromptsListRoute,
    }))
  );

export const promptsRoutes: RouteObject[] = gatePromptsRoutes([
  {
    path: ROUTES.workspace.prompts,
    element: PromptsListRoute ? <PromptsListRoute /> : null,
    errorElement: <ErrorPanel title="Prompts" />,
  },
]);
