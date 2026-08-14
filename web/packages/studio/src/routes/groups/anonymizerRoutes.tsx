// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RouteErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateAnonymizerRoutes, getWorkspaceAnonymizerRoute } from '@studio/routes/utils';
import { UserPen } from 'lucide-react';
import { lazy, type FC } from 'react';
import type { RouteObject } from 'react-router';

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
const AnonymizerJobDetailRoute =
  ANONYMIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/AnonymizerJobDetailRoute').then((m) => ({
      default: m.AnonymizerJobDetailRoute as FC,
    }))
  );

export const anonymizerRoutes: RouteObject[] = gateAnonymizerRoutes([
  {
    path: ROUTES.workspace.anonymizer,
    element: AnonymizerListRoute ? <AnonymizerListRoute /> : null,
    errorElement: <RouteErrorPanel title="Anonymizer" />,
  },
  {
    path: ROUTES.workspace.anonymizerNew,
    element: AnonymizerBuilderRoute ? <AnonymizerBuilderRoute /> : null,
    errorElement: <RouteErrorPanel title="Anonymizer" />,
  },
  {
    path: ROUTES.workspace.anonymizerJob,
    element: AnonymizerJobDetailRoute ? <AnonymizerJobDetailRoute /> : null,
    errorElement: <RouteErrorPanel title="Anonymizer" />,
  },
]);

export const getAnonymizerSideNavItems = (workspace: string) =>
  ANONYMIZER_ENABLED
    ? [
        {
          id: 'anonymizer',
          slotIcon: <UserPen className={iconColorClass} />,
          slotLabel: 'Anonymizer',
          href: getWorkspaceAnonymizerRoute(workspace),
        },
      ]
    : [];
