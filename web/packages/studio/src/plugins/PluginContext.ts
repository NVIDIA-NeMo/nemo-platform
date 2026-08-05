// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { LoadedPlugin, PluginContextValue } from '@studio/plugins/types';
import { createContext, useContext } from 'react';

export const PluginContext = createContext<PluginContextValue>({
  plugins: [],
  installedNames: new Set(),
  isLoaded: false,
  isError: false,
});

export const usePlugins = (): LoadedPlugin[] => useContext(PluginContext).plugins;
export const usePluginsLoaded = (): boolean => useContext(PluginContext).isLoaded;
/** Returns true if the plugin manifest could not be fetched. */
export const usePluginsError = (): boolean => useContext(PluginContext).isError;
/** Returns true if the named plugin is registered in /apis/plugins (with or without a bundle). */
export const usePluginInstalled = (name: string): boolean =>
  useContext(PluginContext).installedNames.has(name);
