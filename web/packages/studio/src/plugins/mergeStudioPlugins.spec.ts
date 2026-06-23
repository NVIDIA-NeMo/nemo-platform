// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { mergeStudioPlugins } from '@studio/plugins/mergeStudioPlugins';

describe('mergeStudioPlugins', () => {
  it('merges manifests and keeps the first registration for duplicate ids', () => {
    const first = [{ id: 'a', name: 'a', contributions: [] }];
    const second = [
      { id: 'a', name: 'a-dup', contributions: [] },
      { id: 'b', name: 'b', contributions: [] },
    ];

    expect(mergeStudioPlugins(first, second).map((plugin) => plugin.id)).toEqual(['a', 'b']);
    expect(mergeStudioPlugins(first, second)[0]?.name).toBe('a');
  });
});
