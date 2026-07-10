// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatDuration } from '@studio/util/duration';

describe('formatDuration', () => {
  it('returns an em dash for null/undefined', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
  });

  it('renders a single millisecond segment under one second', () => {
    expect(formatDuration(34)).toBe('34ms');
    expect(formatDuration(999)).toBe('999ms');
  });

  it('renders seconds and milliseconds', () => {
    expect(formatDuration(12_034)).toBe('12s 34ms');
  });

  it('renders minutes, seconds, and milliseconds', () => {
    expect(formatDuration(612_013)).toBe('10m 12s 13ms');
  });

  it('includes hours for long durations', () => {
    expect(formatDuration(3_661_000)).toBe('1h 1m 1s');
  });

  it('drops trailing zero units', () => {
    expect(formatDuration(12_000)).toBe('12s');
    expect(formatDuration(600_000)).toBe('10m');
  });

  it('keeps interior zero units so the value is unambiguous', () => {
    expect(formatDuration(3_600_000 + 5_000)).toBe('1h 0m 5s');
  });

  it('rounds fractional milliseconds', () => {
    expect(formatDuration(34.6)).toBe('35ms');
  });

  it('keeps precision for sub-millisecond durations', () => {
    expect(formatDuration(0.34)).toBe('0.34ms');
    expect(formatDuration(0.5)).toBe('0.5ms');
  });

  it('renders zero and negative values as 0ms', () => {
    expect(formatDuration(0)).toBe('0ms');
    expect(formatDuration(-5)).toBe('0ms');
  });
});
