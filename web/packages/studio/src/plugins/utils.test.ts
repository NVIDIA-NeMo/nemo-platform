// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isPluginModule, isPluginTraceViewDefinition } from '@studio/plugins/utils';

const Root = () => null;
const View = () => null;
const Activity = () => null;
const navItems = () => [];

describe('plugin module validation', () => {
  it('accepts a plugin with a native trace view and optional activity renderer', () => {
    expect(
      isPluginModule({
        Root,
        navItems,
        traceViews: [{ id: 'semantic-map', label: 'Semantic map', View, Activity }],
      })
    ).toBe(true);
  });

  it('keeps trace views optional for page-only plugins', () => {
    expect(isPluginModule({ Root, navItems })).toBe(true);
  });

  it('rejects malformed and duplicate trace view contributions', () => {
    expect(isPluginTraceViewDefinition({ id: '../escape', label: 'Escape', View })).toBe(false);
    expect(isPluginTraceViewDefinition({ id: 'map', label: '  ', View })).toBe(false);
    expect(isPluginTraceViewDefinition({ id: 'map', label: 'Map', View: 'not-a-component' })).toBe(
      false
    );
    expect(
      isPluginModule({
        Root,
        navItems,
        traceViews: [
          { id: 'map', label: 'Map', View },
          { id: 'map', label: 'Duplicate', View },
        ],
      })
    ).toBe(false);
  });
});
