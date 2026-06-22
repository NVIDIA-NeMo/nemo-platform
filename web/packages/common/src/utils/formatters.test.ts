// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getTextWithCount } from '@nemo/common/src/utils/formatters';

describe('#getTextWithCount', () => {
  it('should return the correct text with count using default suffix', () => {
    expect(getTextWithCount('test', 0)).toBe('0 tests');
    expect(getTextWithCount('test', 1)).toBe('1 test');
    expect(getTextWithCount('test', 2)).toBe('2 tests');
  });

  it('should return the correct text with count using plural', () => {
    expect(getTextWithCount('entry', 0, 'entries')).toBe('0 entries');
    expect(getTextWithCount('entry', 1, 'entries')).toBe('1 entry');
    expect(getTextWithCount('entry', 2, 'entries')).toBe('2 entries');
  });
});
