// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { STUDIO_PLUGINS } from '@studio/plugins/index';
import { PluginScopedRoute } from '@studio/plugins/PluginScopedRoute';
import type {
  SlotContribution,
  SlotId,
  StudioPlugin,
  ViewId,
  ViewOverride,
} from '@studio/plugins/types';
import { getActivePlugins } from '@studio/plugins/workspace';
import { createElement } from 'react';
import type { RouteObject } from 'react-router-dom';

/**
 * Flattens a set of plugins into a per-slot index, ordered by each contribution's `order`
 * (ties keep manifest order, since Array.prototype.sort is stable). Pure and side-effect free
 * so it can be unit-tested with fixture plugins.
 */
export const buildSlotIndex = (
  plugins: readonly StudioPlugin[]
): Map<SlotId, SlotContribution[]> => {
  const index = new Map<SlotId, SlotContribution[]>();
  for (const plugin of plugins) {
    for (const contribution of plugin.contributions) {
      const list = index.get(contribution.slot) ?? [];
      list.push(contribution);
      index.set(contribution.slot, list);
    }
  }
  for (const list of index.values()) {
    list.sort((a, b) => a.order - b.order);
  }
  return index;
};

/**
 * Flattens a set of plugins into a per-view index. When multiple plugins target the same
 * `viewId`, the lowest `order` wins (ties keep manifest order).
 */
export const buildViewIndex = (
  plugins: readonly StudioPlugin[]
): Map<ViewId, ViewOverride> => {
  const candidates = new Map<ViewId, ViewOverride[]>();
  for (const plugin of plugins) {
    for (const override of plugin.viewOverrides ?? []) {
      const list = candidates.get(override.viewId) ?? [];
      list.push(override);
      candidates.set(override.viewId, list);
    }
  }
  const index = new Map<ViewId, ViewOverride>();
  for (const [viewId, list] of candidates) {
    list.sort((a, b) => a.order - b.order);
    index.set(viewId, list[0]!);
  }
  return index;
};

/** Returns the ordered contributions registered for a slot in `workspace` (empty when none). */
export const getSlotContributions = (
  slot: SlotId,
  workspace: string
): readonly SlotContribution[] =>
  buildSlotIndex(getActivePlugins(STUDIO_PLUGINS, workspace)).get(slot) ?? [];

/** Returns the winning view override for `viewId` in `workspace`, if any plugin registered one. */
export const getViewOverride = (viewId: ViewId, workspace: string): ViewOverride | undefined =>
  buildViewIndex(getActivePlugins(STUDIO_PLUGINS, workspace)).get(viewId);

/**
 * Flattens every plugin's `routes` into `RouteObject[]` for the router. The caller merges these
 * under the workspace index (where `path` is resolved) and gates them behind the plugin flag, so
 * an absent or flag-off plugin adds no routes and behavior matches today.
 */
export const collectPluginRoutes = (
  plugins: readonly StudioPlugin[] = STUDIO_PLUGINS
): RouteObject[] =>
  plugins.flatMap((plugin) =>
    (plugin.routes ?? []).map(
      (route): RouteObject => ({
        path: route.path,
        element: createElement(PluginScopedRoute, { plugin, render: route.render }),
      })
    )
  );
