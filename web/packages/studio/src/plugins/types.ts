// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Props passed to a plugin's mount function. */
export interface PluginMountProps {
  /** The workspace the plugin is running within. */
  workspaceId: string;
  /**
   * Auth credentials for the plugin to call backend APIs.
   * Only access tokens are exposed — plugins must not receive refresh tokens.
   */
  auth: {
    accessToken: string;
    getAccessToken: () => string;
  };
  /**
   * The URL base path where Studio is mounted, e.g. `"/studio/"`.
   * Plugins that use their own router (e.g. React Router `BrowserRouter`) must
   * pass this as the `basename` so their routes match the actual browser URL.
   */
  basename: string;
}

/** Cleanup function returned by {@link LoadedPlugin.mount}. */
export type PluginCleanupFn = () => void;

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
 * The plugin is mounted into a container div and unmounted on cleanup.
 */
export interface LoadedPlugin {
  name: string;
  /**
   * Mount the plugin into `container`. Returns a cleanup function that
   * unmounts the plugin and releases all resources.
   */
  mount: (container: HTMLElement, props: PluginMountProps) => PluginCleanupFn;
  /** Return nav items scoped to the given workspace. */
  navItems: (workspaceId: string) => PluginNavGroup[];
}
