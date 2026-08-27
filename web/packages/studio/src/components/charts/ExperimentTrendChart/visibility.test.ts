// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  resolveTrendVisible,
  trendVisibilityStorageKey,
} from '@studio/components/charts/ExperimentTrendChart/visibility';

describe('trendVisibilityStorageKey', () => {
  it('scopes the choice to one experiment', () => {
    expect(trendVisibilityStorageKey('group-id')).toBe('nemo-studio:experiment-trend:group-id');
  });

  it('still returns a usable key before the group has loaded', () => {
    expect(trendVisibilityStorageKey(undefined)).toBe('nemo-studio:experiment-trend:');
  });
});

describe('resolveTrendVisible', () => {
  it('follows the flag when the viewer has never chosen', () => {
    expect(resolveTrendVisible(undefined, true)).toBe(true);
    expect(resolveTrendVisible(undefined, false)).toBe(false);
  });

  it('honours a choice made against the flag as it still reads', () => {
    expect(resolveTrendVisible({ visible: false, flag: true }, true)).toBe(false);
    expect(resolveTrendVisible({ visible: true, flag: false }, false)).toBe(true);
  });

  it('retires a choice made against the opposite flag, so an owner edit takes effect', () => {
    // The reported bug: a viewer had hidden the chart, the owner turned the flag on, and the stale
    // choice kept winning. However the flag moved — modal, API, CLI, another tab — the choice goes.
    expect(resolveTrendVisible({ visible: false, flag: false }, true)).toBe(true);
    expect(resolveTrendVisible({ visible: true, flag: true }, false)).toBe(false);
  });

  it('ignores the older bare-boolean format rather than stranding viewers on it', () => {
    expect(resolveTrendVisible(false, true)).toBe(true);
    expect(resolveTrendVisible(true, false)).toBe(false);
  });

  it('ignores anything malformed, falling back to the flag', () => {
    expect(resolveTrendVisible(null, true)).toBe(true);
    expect(resolveTrendVisible('false', true)).toBe(true);
    expect(resolveTrendVisible({ visible: 'no', flag: true }, true)).toBe(true);
    expect(resolveTrendVisible({ visible: false }, true)).toBe(true);
  });
});
