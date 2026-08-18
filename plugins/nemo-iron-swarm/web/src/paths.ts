// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Links must be absolute: Studio mounts plugins at a splat route, and React
// Router resolves a relative `to` against the full matched path, so it appends.
// Route `path`s below are relative — only `to` / `href` need the prefix.

const base = (workspace: string): string => `/workspaces/${workspace}/plugin/iron-swarm`;

/** Route `path` values for the plugin's own <Routes>, relative to the mount. */
export const ROUTE_PATHS = {
  runList: '',
  runDetails: ':ironSwarmRunName',
  manifestList: 'manifests',
  manifestNew: 'manifests/new',
  manifestDetail: 'manifests/:ironSwarmManifestName',
} as const;

export const getIronSwarmRunListRoute = (workspace: string): string => base(workspace);

export const getIronSwarmRunDetailsRoute = (workspace: string, ironSwarmRunName: string): string =>
  `${base(workspace)}/${encodeURIComponent(ironSwarmRunName)}`;

export const getIronSwarmManifestListRoute = (workspace: string): string =>
  `${base(workspace)}/manifests`;

export const getNewIronSwarmManifestRoute = (workspace: string): string =>
  `${base(workspace)}/manifests/new`;

export const getIronSwarmManifestDetailRoute = (
  workspace: string,
  ironSwarmManifestName: string
): string => `${base(workspace)}/manifests/${encodeURIComponent(ironSwarmManifestName)}`;

/** Studio routes the plugin links out to. */
export const getSecretsRoute = (workspace: string): string => `/workspaces/${workspace}/secrets`;
