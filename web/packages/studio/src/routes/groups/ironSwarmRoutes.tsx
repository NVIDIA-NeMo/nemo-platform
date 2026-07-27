// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { IRON_SWARM_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { gateIronSwarmRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const IronSwarmRunListRoute =
  IRON_SWARM_ENABLED &&
  lazy(() =>
    import('@studio/routes/IronSwarmRunListRoute').then((m) => ({
      default: m.IronSwarmRunListRoute,
    }))
  );
const IronSwarmRunDetailsRoute =
  IRON_SWARM_ENABLED &&
  lazy(() =>
    import('@studio/routes/IronSwarmRunDetailsRoute').then((m) => ({
      default: m.IronSwarmRunDetailsRoute,
    }))
  );
const IronSwarmManifestListRoute =
  IRON_SWARM_ENABLED &&
  lazy(() =>
    import('@studio/routes/IronSwarmManifestListRoute').then((m) => ({
      default: m.IronSwarmManifestListRoute,
    }))
  );
const NewIronSwarmManifestRoute =
  IRON_SWARM_ENABLED &&
  lazy(() =>
    import('@studio/routes/NewIronSwarmManifestRoute').then((m) => ({
      default: m.NewIronSwarmManifestRoute,
    }))
  );
const IronSwarmManifestDetailRoute =
  IRON_SWARM_ENABLED &&
  lazy(() =>
    import('@studio/routes/IronSwarmManifestDetailRoute').then((m) => ({
      default: m.IronSwarmManifestDetailRoute,
    }))
  );

export const ironSwarmRoutes: RouteObject[] = gateIronSwarmRoutes([
  {
    path: ROUTES.workspace.ironSwarmRunList,
    element: IronSwarmRunListRoute ? <IronSwarmRunListRoute /> : null,
    errorElement: <ErrorPanel title="Iron Swarm" />,
  },
  {
    path: ROUTES.workspace.ironSwarmManifestList,
    element: IronSwarmManifestListRoute ? <IronSwarmManifestListRoute /> : null,
    errorElement: <ErrorPanel title="Iron Swarm" />,
  },
  {
    path: ROUTES.workspace.ironSwarmManifestNew,
    element: NewIronSwarmManifestRoute ? <NewIronSwarmManifestRoute /> : null,
    errorElement: <ErrorPanel title="Iron Swarm" />,
  },
  {
    path: ROUTES.workspace.ironSwarmManifestDetail,
    element: IronSwarmManifestDetailRoute ? <IronSwarmManifestDetailRoute /> : null,
    errorElement: <ErrorPanel title="Iron Swarm" />,
  },
  {
    path: ROUTES.workspace.ironSwarmRunDetails,
    element: IronSwarmRunDetailsRoute ? <IronSwarmRunDetailsRoute /> : null,
    errorElement: <ErrorPanel title="Iron Swarm" />,
  },
]);
