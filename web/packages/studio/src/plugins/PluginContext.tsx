// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { isTrustedBundleUrl } from '@studio/plugins/security';
import type { LoadedPlugin, PluginManifest } from '@studio/plugins/types';
import { logger } from '@studio/util/logger';
import { useQuery } from '@tanstack/react-query';
import { createContext, type ReactNode, useContext } from 'react';

interface PluginContextValue {
  plugins: LoadedPlugin[];
  /** All plugin names returned by /apis/plugins, including headless ones. */
  installedNames: ReadonlySet<string>;
  isLoaded: boolean;
  isError: boolean;
}

const PluginContext = createContext<PluginContextValue>({
  plugins: [],
  installedNames: new Set(),
  isLoaded: false,
  isError: false,
});

// eslint-disable-next-line react-refresh/only-export-components
export const usePlugins = (): LoadedPlugin[] => useContext(PluginContext).plugins;
// eslint-disable-next-line react-refresh/only-export-components
export const usePluginsLoaded = (): boolean => useContext(PluginContext).isLoaded;
/** Returns true if the plugin manifest could not be fetched. */
// eslint-disable-next-line react-refresh/only-export-components
export const usePluginsError = (): boolean => useContext(PluginContext).isError;
/** Returns true if the named plugin is registered in /apis/plugins (with or without a bundle). */
// eslint-disable-next-line react-refresh/only-export-components
export const usePluginInstalled = (name: string): boolean =>
  useContext(PluginContext).installedNames.has(name);

function isValidPluginManifest(obj: unknown): obj is PluginManifest {
  if (typeof obj !== 'object' || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return typeof o.name === 'string' && (typeof o.bundleUrl === 'string' || o.bundleUrl === null);
}

interface PluginModule {
  mount: LoadedPlugin['mount'];
  navItems: LoadedPlugin['navItems'];
}

function isPluginModule(mod: unknown): mod is PluginModule {
  if (typeof mod !== 'object' || mod === null) return false;
  const m = mod as Record<string, unknown>;
  return typeof m.mount === 'function' && typeof m.navItems === 'function';
}

async function loadPlugin(manifest: PluginManifest, baseUrl: string): Promise<LoadedPlugin | null> {
  if (manifest.bundleUrl === null) {
    // Plugin registered without a web bundle — no UI to mount or nav to show.
    return null;
  }
  if (!isTrustedBundleUrl(manifest.bundleUrl)) {
    logger.warn(`[plugins] Rejected untrusted bundle URL: ${manifest.bundleUrl}`);
    return null;
  }
  // Prefix with the API base URL so the import resolves against the backend
  // host, not the Studio dev server (which may run on a different origin).
  const absoluteUrl = `${baseUrl}${manifest.bundleUrl}`;
  try {
    const module: unknown = await import(/* @vite-ignore */ absoluteUrl);
    if (!isPluginModule(module)) {
      logger.warn(`[plugins] Plugin "${manifest.name}" missing required exports (mount, navItems)`);
      return null;
    }
    return { name: manifest.name, mount: module.mount, navItems: module.navItems };
  } catch (err) {
    logger.warn(`[plugins] Failed to load plugin "${manifest.name}":`, err);
    return null;
  }
}

interface PluginQueryData {
  plugins: LoadedPlugin[];
  installedNames: ReadonlySet<string>;
}

async function fetchPlugins(): Promise<PluginQueryData> {
  // Falls back to same-origin when PLATFORM_BASE_URL is not configured
  const baseUrl = PLATFORM_BASE_URL ?? '';
  const res = await fetch(`${baseUrl}/apis/plugins`);
  if (!res.ok) throw new Error(`/apis/plugins returned ${res.status}`);
  const data: unknown = await res.json();
  if (!Array.isArray(data)) {
    // Throw (not empty-success) so a malformed manifest fails open like a
    // network error, rather than masquerading as "no plugins installed".
    logger.warn('[plugins] /apis/plugins did not return an array');
    throw new Error('/apis/plugins did not return an array');
  }
  const invalid = (data as unknown[]).filter((item) => !isValidPluginManifest(item));
  if (invalid.length > 0) {
    logger.warn(
      `[plugins] /apis/plugins returned ${invalid.length} invalid manifest(s) — skipping`
    );
  }
  const manifests = (data as unknown[]).filter(isValidPluginManifest);
  const loaded = await Promise.all(manifests.map((m) => loadPlugin(m, baseUrl)));
  return {
    installedNames: new Set(manifests.map((m) => m.name)),
    plugins: loaded.filter((p): p is LoadedPlugin => p !== null),
  };
}

const NO_PLUGINS: LoadedPlugin[] = [];
const NO_NAMES: ReadonlySet<string> = new Set();

interface PluginProviderProps {
  children: ReactNode;
}

export const PluginProvider = ({ children }: PluginProviderProps) => {
  const { data, isSuccess, isError } = useQuery({
    queryKey: ['plugins', 'manifest'],
    queryFn: fetchPlugins,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnReconnect: false,
  });

  return (
    <PluginContext.Provider
      value={{
        plugins: data?.plugins ?? NO_PLUGINS,
        installedNames: data?.installedNames ?? NO_NAMES,
        isLoaded: isSuccess || isError,
        isError,
      }}
    >
      {children}
    </PluginContext.Provider>
  );
};
