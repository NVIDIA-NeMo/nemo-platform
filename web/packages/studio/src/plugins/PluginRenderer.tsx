// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { PluginErrorBoundary } from '@studio/plugins/PluginErrorBoundary';
import { usePluginHost } from '@studio/plugins/usePluginHost';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { useEffect, type ReactElement } from 'react';
import { useParams } from 'react-router';

// Renders the active plugin's `Root` as a normal child (not a detached
// `createRoot`) so it shares Studio's Router, QueryClient, and theme.
export const PluginRenderer = (): ReactElement => {
  const { pluginName } = useParams<{ pluginName: string }>();
  const plugins = usePlugins();
  const isLoaded = usePluginsLoaded();
  const host = usePluginHost(pluginName ?? 'unknown');

  const plugin = plugins.find((p) => p.name === pluginName);
  const { setBreadcrumbs } = useBreadcrumbs();
  // Studio owns the cleanup so a plugin can't leave a stale trail behind. Keyed
  // on pluginName too: the router reuses this component across plugins, and the
  // outgoing plugin's trail would otherwise persist until the next one sets its own.
  useEffect(() => () => setBreadcrumbs([]), [setBreadcrumbs, pluginName]);

  if (!isLoaded) {
    return (
      <div className="flex h-full items-center justify-center text-subtle">Loading plugin…</div>
    );
  }

  if (!plugin) {
    return (
      <div className="flex h-full items-center justify-center text-subtle">
        Plugin &ldquo;{pluginName}&rdquo; not found.
      </div>
    );
  }

  const { Root } = plugin;
  return (
    <div className="size-full">
      <PluginErrorBoundary pluginName={plugin.name}>
        <Root host={host} />
      </PluginErrorBoundary>
    </div>
  );
};
