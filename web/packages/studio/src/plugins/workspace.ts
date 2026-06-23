// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StudioPlugin } from '@studio/plugins/types';

/** Workspaces plugins apply to when `workspaces` is omitted on the manifest. */
export const DEFAULT_PLUGIN_WORKSPACES = ['default'] as const;

/**
 * Returns whether `plugin` should be active for the given workspace route param
 * (`/workspaces/:workspace/...`).
 */
export const isPluginActive = (plugin: StudioPlugin, workspace: string): boolean => {
  const scope = plugin.workspaces ?? DEFAULT_PLUGIN_WORKSPACES;
  if (scope === 'all') {
    return true;
  }
  return scope.includes(workspace);
};

/** Filters a plugin list to those active in `workspace`. */
export const getActivePlugins = (
  plugins: readonly StudioPlugin[],
  workspace: string
): readonly StudioPlugin[] => plugins.filter((plugin) => isPluginActive(plugin, workspace));
