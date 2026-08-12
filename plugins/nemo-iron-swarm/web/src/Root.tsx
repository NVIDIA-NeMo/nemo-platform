// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0


import { configureClient } from '@iron-swarm/api/fetcher';
import { HostProvider } from '@iron-swarm/host';
import { ROUTE_PATHS } from '@iron-swarm/paths';
import { IronSwarmManifestDetailRoute } from '@iron-swarm/routes/IronSwarmManifestDetailRoute';
import { IronSwarmManifestListRoute } from '@iron-swarm/routes/IronSwarmManifestListRoute';
import { IronSwarmRunDetailsRoute } from '@iron-swarm/routes/IronSwarmRunDetailsRoute';
import { IronSwarmRunListRoute } from '@iron-swarm/routes/IronSwarmRunListRoute';
import { NewIronSwarmManifestRoute } from '@iron-swarm/routes/NewIronSwarmManifestRoute';
import type { PluginRootProps } from '@iron-swarm/types';
import { Route, Routes } from 'react-router';

/**
 * Iron Swarm plugin root.
 *
 * Studio renders this inside its own React tree — same Router, QueryClient, and
 * KaizenThemeProvider — so the routes below are plain `<Route>`s relative to the
 * plugin's mount point and the tables come from Studio's shared `@nemo/common`.
 *
 * The generated iron-swarm client is the plugin's own (Studio's SDK only covers
 * platform services), so it is pointed at the host's token getter here. This runs
 * during render rather than in an effect because child routes issue requests on
 * their first render, before an effect would have fired.
 */
export function Root({ host }: PluginRootProps) {
  configureClient({ getAccessToken: host.auth.getAccessToken, baseUrl: host.apiBaseUrl });

  return (
    <HostProvider host={host}>
      <Routes>
        <Route path={ROUTE_PATHS.runList} element={<IronSwarmRunListRoute />} />
        <Route path={ROUTE_PATHS.manifestList} element={<IronSwarmManifestListRoute />} />
        <Route path={ROUTE_PATHS.manifestNew} element={<NewIronSwarmManifestRoute />} />
        <Route path={ROUTE_PATHS.manifestDetail} element={<IronSwarmManifestDetailRoute />} />
        <Route path={ROUTE_PATHS.runDetails} element={<IronSwarmRunDetailsRoute />} />
      </Routes>
    </HostProvider>
  );
}
