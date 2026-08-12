// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { logger } from '@nemo/common/src/utils/logger';
import * as agentsSdk from '@nemo/sdk/generated/agents/api';
import * as platformSdk from '@nemo/sdk/generated/platform/api';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type {
  PluginBreadcrumb,
  PluginHost,
  PluginSdk,
  PluginTelemetry,
} from '@studio/plugins/types';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { useCallback, useMemo, useRef } from 'react';
import { useAuth } from 'react-oidc-context';
import { useNavigate } from 'react-router';

// Module-scope for stable identity; plugins run these on Studio's axios + cache.
const STUDIO_SDK: PluginSdk = { platform: platformSdk, agents: agentsSdk };

const makeTelemetry = (name: string): PluginTelemetry => ({
  info: (message, cause) => logger.info(`[plugin:${name}] ${message}`, cause),
  warn: (message, cause) => logger.warn(`[plugin:${name}] ${message}`, cause),
  error: (message, cause) => logger.error(`[plugin:${name}] ${message}`, cause),
  event: (event, attributes) => logger.info(`[plugin:${name}] event:${event}`, attributes),
});

/** Build the host handle for both plugin pages and embedded plugin surfaces. */
export const usePluginHost = (pluginName: string): PluginHost => {
  const workspace = useWorkspaceFromPath();
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const { setBreadcrumbs } = useBreadcrumbs();
  const accessToken = user?.access_token ?? '';
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;
  const getAccessToken = useCallback(() => accessTokenRef.current, []);
  const setPluginBreadcrumbs = useCallback(
    (trail: PluginBreadcrumb[]) =>
      setBreadcrumbs(trail.map(({ label, href }) => ({ slotLabel: label, href }))),
    [setBreadcrumbs]
  );

  return useMemo<PluginHost>(
    () => ({
      workspaceId: workspace,
      apiBaseUrl: PLATFORM_BASE_URL ?? '',
      auth: { accessToken, getAccessToken },
      sdk: STUDIO_SDK,
      navigation: { navigate: (to) => navigate(to), back: () => navigate(-1) },
      notifications: { notify: (message, type = 'info', options) => toast[type](message, options) },
      telemetry: makeTelemetry(pluginName),
      breadcrumbs: { set: setPluginBreadcrumbs },
    }),
    [workspace, accessToken, getAccessToken, navigate, toast, pluginName, setPluginBreadcrumbs]
  );
};
