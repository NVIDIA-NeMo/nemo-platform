// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateAnonymizerRoutes } from '@studio/routes/utils';
import { FC, lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const AnonymizerListRoute =
  ANONYMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/AnonymizerListRoute').then((m) => ({
      default: m.AnonymizerListRoute as FC,
    }))
  );
const AnonymizerBuilderRoute =
  ANONYMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/AnonymizerBuilderRoute').then((m) => ({
      default: m.AnonymizerBuilderRoute as FC,
    }))
  );

export const anonymizerRoutes: RouteObject[] = gateAnonymizerRoutes([
  {
    path: ROUTES.workspace.anonymizer,
    element: AnonymizerListRoute ? <AnonymizerListRoute /> : null,
    errorElement: <ErrorPanel title="Anonymizer" />,
  },
  {
    path: ROUTES.workspace.anonymizerNew,
    element: AnonymizerBuilderRoute ? <AnonymizerBuilderRoute /> : null,
    errorElement: <ErrorPanel title="Anonymizer" />,
  },
  {
    path: ROUTES.workspace.anonymizerJob,
    element: AnonymizerBuilderRoute ? <AnonymizerBuilderRoute /> : null,
    errorElement: <ErrorPanel title="Anonymizer" />,
  },
]);
