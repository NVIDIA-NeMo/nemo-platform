// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Links must be absolute: Studio mounts plugins at a splat route, and React
// Router resolves a relative `to` against the full matched path, so it appends.
export const pluginPath = (workspaceId: string, page: string): string =>
  `/workspaces/${workspaceId}/plugin/example/${page}`;

export const PAGES = ['overview', 'auth', 'workspace', 'shared-ui'] as const;

export const PAGE_LABELS: Record<(typeof PAGES)[number], string> = {
  overview: 'Overview',
  auth: 'Auth',
  workspace: 'Workspace',
  'shared-ui': 'Shared UI',
};
