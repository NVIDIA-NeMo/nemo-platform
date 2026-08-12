// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { logger } from '@nemo/common/src/utils/logger';
import * as platformSdk from '@nemo/sdk/generated/platform/api';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { PluginErrorBoundary } from '@studio/plugins/PluginErrorBoundary';
import type {
  PluginBreadcrumb,
  PluginHost,
  PluginSdk,
  PluginTelemetry,
} from '@studio/plugins/types';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { useCallback, useEffect, useMemo, useRef, type ReactElement } from 'react';
import { useAuth } from 'react-oidc-context';
import { useNavigate, useParams } from 'react-router';

// Module-scope for stable identity; plugins run these on Studio's axios + cache.
const STUDIO_SDK: PluginSdk = { platform: platformSdk };

const makeTelemetry = (name: string): PluginTelemetry => ({
  info: (message, cause) => logger.info(`[plugin:${name}] ${message}`, cause),
  warn: (message, cause) => logger.warn(`[plugin:${name}] ${message}`, cause),
  error: (message, cause) => logger.error(`[plugin:${name}] ${message}`, cause),
  event: (event, attributes) => logger.info(`[plugin:${name}] event:${event}`, attributes),
});

// Renders the active plugin's `Root` as a normal child (not a detached
// `createRoot`) so it shares Studio's Router, QueryClient, and theme.
export const PluginRenderer = (): ReactElement => {
  const { pluginName } = useParams<{ pluginName: string }>();
  const plugins = usePlugins();
  const isLoaded = usePluginsLoaded();
  const workspace = useWorkspaceFromPath();
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  const plugin = plugins.find((p) => p.name === pluginName);
  const accessToken = user?.access_token ?? '';
  // Keep the latest token in a ref so getAccessToken has a stable identity but
  // still returns the current token after OIDC silent renew.
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;
  const getAccessToken = useCallback(() => accessTokenRef.current, []);

  const { setBreadcrumbs } = useBreadcrumbs();
  const setPluginBreadcrumbs = useCallback(
    (trail: PluginBreadcrumb[]) =>
      setBreadcrumbs(trail.map(({ label, href }) => ({ slotLabel: label, href }))),
    [setBreadcrumbs]
  );
  // Studio owns the cleanup so a plugin can't leave a stale trail behind. Keyed
  // on pluginName too: the router reuses this component across plugins, and the
  // outgoing plugin's trail would otherwise persist until the next one sets its own.
  useEffect(() => () => setBreadcrumbs([]), [setBreadcrumbs, pluginName]);

  const host = useMemo<PluginHost>(
    () => ({
      workspaceId: workspace,
      auth: { accessToken, getAccessToken },
      sdk: STUDIO_SDK,
      navigation: { navigate: (to) => navigate(to), back: () => navigate(-1) },
      notifications: { notify: (message, type = 'info', options) => toast[type](message, options) },
      telemetry: makeTelemetry(pluginName ?? 'unknown'),
      breadcrumbs: { set: setPluginBreadcrumbs },
    }),
    [workspace, accessToken, getAccessToken, navigate, toast, pluginName, setPluginBreadcrumbs]
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
      <PluginErrorBoundary pluginName={plugin.name}>
        <Root host={host} />
      </PluginErrorBoundary>
    </div>
  );
};
