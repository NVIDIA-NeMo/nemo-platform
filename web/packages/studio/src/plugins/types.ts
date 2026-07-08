// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ComponentType, ReactNode } from 'react';

/** Props passed to a plugin's root component. */
export interface PluginRootProps {
  /** The workspace the plugin is running within. */
  workspaceId: string;
  /**
   * Auth credentials for the plugin to call backend APIs.
   * Only access tokens are exposed — plugins must not receive refresh tokens,
   * which is why auth is passed as a prop rather than via Studio's OIDC context.
   */
  auth: {
    accessToken: string;
    getAccessToken: () => string;
  };
}

/** API manifest returned by `GET /apis/plugins`. */
export interface PluginManifest {
  name: string;
  /** `null` for plugins registered without a web bundle. */
  bundleUrl: string | null;
}

/** A single navigation item contributed by a plugin. */
export interface PluginNavItem {
  id: string;
  /** Kebab-case Lucide icon name, e.g. `"flask-conical"`. */
  iconName: string;
  label: string;
  /**
   * Absolute path relative to the app root, e.g.
   * `/workspaces/:workspaceId/plugin/example/dashboard`.
   */
  href: string;
}

/** A group of navigation items contributed by a plugin. */
export interface PluginNavGroup {
  group: string;
  items: PluginNavItem[];
}

/**
 * A plugin bundle loaded at runtime via dynamic `import()`.
 *
 * The plugin's `Root` is rendered *inside* Studio's React tree — under the same
 * Router, QueryClient, and theme providers — so the plugin shares those contexts
 * (e.g. it navigates with Studio's router instead of standing up its own). The
 * plugin still ships as a separately-built bundle with its own private deps; only
 * the context-bearing singletons (react, react-dom, react-router) are shared via
 * the runtime import map.
 */
export interface LoadedPlugin {
  name: string;
  /** The plugin's root component, rendered within Studio's provider tree. */
  Root: ComponentType<PluginRootProps>;
  /** Return nav items scoped to the given workspace. */
  navItems: (workspaceId: string) => PluginNavGroup[];
}

/** The exports a loaded plugin bundle module must expose. */
export interface PluginModule {
  Root: LoadedPlugin['Root'];
  navItems: LoadedPlugin['navItems'];
}

/** Result of fetching the manifest and loading each plugin's bundle. */
export interface PluginQueryData {
  plugins: LoadedPlugin[];
  installedNames: ReadonlySet<string>;
}

/** Value exposed by the plugin React context. */
export interface PluginContextValue {
  plugins: LoadedPlugin[];
  /** All plugin names returned by /apis/plugins, including headless ones. */
  installedNames: ReadonlySet<string>;
  isLoaded: boolean;
  isError: boolean;
}

/** Props for the plugin context provider. */
export interface PluginProviderProps {
  children: ReactNode;
}
