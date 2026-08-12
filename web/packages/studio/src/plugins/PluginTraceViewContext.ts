// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { usePlugins } from '@studio/plugins/PluginContext';
import type { PluginTraceViewDefinition, PluginTraceViewMode } from '@studio/plugins/types';
import { useMemo } from 'react';

export interface ResolvedPluginTraceView extends PluginTraceViewDefinition {
  pluginName: string;
  mode: PluginTraceViewMode;
}

export const usePluginTraceViews = (): ResolvedPluginTraceView[] => {
  const plugins = usePlugins();
  return useMemo(
    () =>
      plugins.flatMap((plugin) =>
        (plugin.traceViews ?? []).map((view) => ({
          ...view,
          pluginName: plugin.name,
          mode: `plugin:${plugin.name}:${view.id}` as const,
        }))
      ),
    [plugins]
  );
};
