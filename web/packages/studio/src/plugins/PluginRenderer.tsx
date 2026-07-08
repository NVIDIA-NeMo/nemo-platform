// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import type { PluginRootProps } from '@studio/plugins/types';
import { useCallback, useMemo, useRef, type ReactElement } from 'react';
import { useAuth } from 'react-oidc-context';
import { useParams } from 'react-router-dom';

/**
 * Renders the active plugin's `Root` component inside Studio's React tree.
 *
 * The plugin is rendered as a normal child component — not mounted into a
 * detached `createRoot` — so it shares Studio's Router, QueryClient, and theme
 * contexts. A render error in the plugin is contained by the plugin route's
 * `errorElement` (see the route definition in `routes/index.tsx`), which keeps a
 * misbehaving plugin from taking down the rest of Studio.
 */
export const PluginRenderer = (): ReactElement => {
  const { pluginName } = useParams<{ pluginName: string }>();
  const plugins = usePlugins();
  const isLoaded = usePluginsLoaded();
  const workspace = useWorkspaceFromPath();
  const { user } = useAuth();

  const plugin = plugins.find((p) => p.name === pluginName);
  const accessToken = user?.access_token ?? '';
  // Keep the latest token in a ref so getAccessToken has a stable identity but
  // still returns the current token after OIDC silent renew.
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;
  const getAccessToken = useCallback(() => accessTokenRef.current, []);

  const auth = useMemo<PluginRootProps['auth']>(
    () => ({ accessToken, getAccessToken }),
    [accessToken, getAccessToken]
  );

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
      <Root workspaceId={workspace} auth={auth} />
    </div>
  );
};
