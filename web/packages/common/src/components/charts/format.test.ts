// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  formatNumericValue,
  formatXValueDefault,
  inferXAxisType,
  seriesColor,
  toPlotValue,
} from '@nemo/common/src/components/charts/format';
import { SERIES_COLORS } from '@nemo/common/src/components/charts/tokens';

describe('chart tokens', () => {
  /**
   * Pinned in full: every chart assigns color by index, so reordering this list silently
   * recolors all of them and no rendering test would fail.
   */
  it('keeps the series palette stable and in order', () => {
    expect(SERIES_COLORS).toEqual([
      'var(--text-color-accent-blue)',
      'var(--text-color-accent-green)',
      'var(--text-color-accent-purple)',
      'var(--text-color-accent-yellow)',
      'var(--text-color-accent-teal)',
      'var(--text-color-accent-red)',
      'var(--text-color-accent-gray)',
    ]);
  });
});

describe('seriesColor', () => {
  it('prefers an explicit series color over the palette', () => {
    expect(seriesColor({ color: '#fff' }, 0)).toBe('#fff');
  });

  it('assigns palette colors by index', () => {
    expect(seriesColor({}, 0)).toBe('var(--text-color-accent-blue)');
    expect(seriesColor({}, 2)).toBe('var(--text-color-accent-purple)');
  });

  it('wraps around past the end of the palette', () => {
    expect(seriesColor({}, SERIES_COLORS.length)).toBe(SERIES_COLORS[0]);
    expect(seriesColor({}, SERIES_COLORS.length + 2)).toBe(SERIES_COLORS[2]);
  });

  it('accepts a caller series type without tripping excess-property checks', () => {
    expect(seriesColor({ id: 'a', label: 'A', data: [1] }, 1)).toBe(
      'var(--text-color-accent-green)'
    );
    expect(seriesColor({ id: 'a', label: 'A', lower: [0], upper: [1] }, 1)).toBe(
      'var(--text-color-accent-green)'
    );
  });
});

describe('inferXAxisType', () => {
  it('infers the axis type from the first x value', () => {
    expect(inferXAxisType(['a', 'b'])).toBe('category');
    expect(inferXAxisType([1, 2])).toBe('number');
    expect(inferXAxisType([new Date(0)])).toBe('time');
  });

  it('falls back to category for an empty axis', () => {
    expect(inferXAxisType([])).toBe('category');
  });
});

describe('toPlotValue', () => {
  it('converts dates to timestamps and passes everything else through', () => {
    expect(toPlotValue(new Date(0))).toBe(0);
    expect(toPlotValue(42)).toBe(42);
    expect(toPlotValue('Step 1')).toBe('Step 1');
  });
});

describe('formatNumericValue', () => {
  it('compacts large values and keeps small ones precise', () => {
    expect(formatNumericValue(16000)).toBe('16K');
    expect(formatNumericValue(0.1234)).toBe('0.123');
  });
});

describe('formatXValueDefault', () => {
  it('formats numbers, strings, and dates', () => {
    expect(formatXValueDefault(16000)).toBe('16K');
    expect(formatXValueDefault('Step 1')).toBe('Step 1');
    expect(formatXValueDefault(new Date(0))).toContain('Jan');
  });
});
