// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RouteErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { SAFE_SYNTHESIZER_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import { gateSafeSynthesizerRoutes, getWorkspaceSafeSynthesizerRoute } from '@studio/routes/utils';
import { DatabaseCheck } from 'lucide-react';
import { FC, lazy } from 'react';
import type { RouteObject } from 'react-router';

const SafeSynthesizerListRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerListRoute').then((m) => ({
      default: m.SafeSynthesizerListRoute as FC,
    }))
  );
const SafeSynthesizerNewRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerNewRoute').then((m) => ({
      default: m.SafeSynthesizerNewRoute as FC,
    }))
  );
const SafeSynthesizerJobDetailsRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerJobDetailsRoute').then((m) => ({
      default: m.SafeSynthesizerJobDetailsRoute as FC,
    }))
  );
const SafeSynthesizerJobReportRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerJobReportRoute').then((m) => ({
      default: m.SafeSynthesizerJobReportRoute as FC,
    }))
  );

export const safeSynthesizerRoutes: RouteObject[] = gateSafeSynthesizerRoutes([
  {
    path: ROUTES.workspace.safeSynthesizer,
    element: SafeSynthesizerListRoute ? <SafeSynthesizerListRoute /> : null,
    errorElement: <RouteErrorPanel title="Safe Synthesizer" />,
  },
  {
    path: ROUTES.workspace.safeSynthesizerNew,
    element: SafeSynthesizerNewRoute ? <SafeSynthesizerNewRoute /> : null,
    errorElement: <RouteErrorPanel title="Safe Synthesizer" />,
  },
  {
    path: ROUTES.workspace.safeSynthesizerJob,
    element: SafeSynthesizerJobDetailsRoute ? <SafeSynthesizerJobDetailsRoute /> : null,
    errorElement: <RouteErrorPanel title="Safe Synthesizer" />,
  },
  {
    path: ROUTES.workspace.safeSynthesizerJobReport,
    element: SafeSynthesizerJobReportRoute ? <SafeSynthesizerJobReportRoute /> : null,
    errorElement: <RouteErrorPanel title="Safe Synthesizer" />,
  },
]);

export const getSafeSynthesizerSideNavItems = (workspace: string) =>
  SAFE_SYNTHESIZER_ENABLED
    ? [
        {
          id: 'safeSynthesizer',
          slotIcon: <DatabaseCheck className={iconColorClass} />,
          slotLabel: 'Safe Synthesizer',
          href: getWorkspaceSafeSynthesizerRoute(workspace),
        },
      ]
    : [];
