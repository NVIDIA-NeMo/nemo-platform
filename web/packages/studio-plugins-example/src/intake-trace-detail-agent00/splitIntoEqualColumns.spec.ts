// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { splitIntoEqualColumns } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/splitIntoEqualColumns';

describe('splitIntoEqualColumns', () => {
  it('returns an empty array for no items', () => {
    expect(splitIntoEqualColumns([], 3)).toEqual([]);
  });

  it('distributes items so column sizes differ by at most one', () => {
    expect(splitIntoEqualColumns(['a', 'b', 'c', 'd', 'e', 'f', 'g'], 3)).toEqual([
      ['a', 'b', 'c'],
      ['d', 'e'],
      ['f', 'g'],
    ]);
  });

  it('keeps a single item in the first column', () => {
    expect(splitIntoEqualColumns(['only'], 3)).toEqual([['only'], [], []]);
  });
});
