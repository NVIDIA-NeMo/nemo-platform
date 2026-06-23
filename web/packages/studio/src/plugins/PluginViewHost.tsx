// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { featureFlags } from '@studio/constants/featureFlags';
import { getViewOverride } from '@studio/plugins/registry';
import type { ViewContextMap, ViewId } from '@studio/plugins/types';
import type { ComponentType } from 'react';

interface PluginViewHostProps<V extends ViewId> {
  viewId: V;
  /** Typed context the default view and any override both receive. */
  context: ViewContextMap[V];
  /** First-party view rendered when the plugin flag is off or no override is registered. */
  fallback: ComponentType<ViewContextMap[V]>;
}

/**
 * Renders a plugin view override when the experiment-plugins flag is on and a plugin registered
 * for `viewId`; otherwise renders `fallback` unchanged. Host routes stay thin: resolve params,
 * build context, delegate here.
 */
export const PluginViewHost = <V extends ViewId>({
  viewId,
  context,
  fallback: Fallback,
}: PluginViewHostProps<V>) => {
  if (featureFlags.experimentPlugins) {
    const override = getViewOverride(viewId, context.workspace);
    if (override) {
      const Override = override.render as ComponentType<ViewContextMap[V]>;
      return <Override {...context} />;
    }
  }

  return <Fallback {...context} />;
};
