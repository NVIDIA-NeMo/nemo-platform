// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Absolute paths for this plugin's pages.
 *
 * Studio mounts plugins at a splat route (`/plugin/:pluginName/*`), and React
 * Router resolves a relative `to` against the splat's *full* matched pathname.
 * So `to="overview"` appends to the current page instead of replacing it —
 * `/plugin/example/auth/overview`. Links must be absolute.
 */
export const pluginPath = (workspaceId: string, page: string): string =>
  `/workspaces/${workspaceId}/plugin/example/${page}`;

export const PAGES = ['overview', 'auth', 'workspace', 'shared-ui'] as const;

export const PAGE_LABELS: Record<(typeof PAGES)[number], string> = {
  overview: 'Overview',
  auth: 'Auth',
  workspace: 'Workspace',
  'shared-ui': 'Shared UI',
};
