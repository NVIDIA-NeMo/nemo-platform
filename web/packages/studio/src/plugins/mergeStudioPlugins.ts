// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StudioPlugin } from '@studio/plugins/types';

/** Merges plugin manifests; first registration wins when ids collide. */
export const mergeStudioPlugins = (
  ...sources: readonly (readonly StudioPlugin[])[]
): readonly StudioPlugin[] => {
  const merged: StudioPlugin[] = [];
  const seen = new Set<string>();

  for (const plugins of sources) {
    for (const plugin of plugins) {
      if (seen.has(plugin.id)) {
        continue;
      }
      seen.add(plugin.id);
      merged.push(plugin);
    }
  }

  return merged;
};
