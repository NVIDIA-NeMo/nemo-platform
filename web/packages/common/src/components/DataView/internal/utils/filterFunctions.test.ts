// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { filterFunctions } from '@nemo/common/src/components/DataView/internal/utils/filterFunctions';
import type { Row } from '@tanstack/react-table';

/** Minimal row stub exposing just the getValue the filter functions read. */
const rowWith = (value: unknown): Row<unknown> =>
  ({ getValue: () => value }) as unknown as Row<unknown>;

describe('filterFunctions.numberRange', () => {
  const { numberRange } = filterFunctions;

  it('keeps rows within the inclusive bounds', () => {
    expect(numberRange(rowWith(50), 'v', { $gte: 10, $lte: 100 }, () => {})).toBe(true);
    expect(numberRange(rowWith(10), 'v', { $gte: 10, $lte: 100 }, () => {})).toBe(true); // inclusive lower
    expect(numberRange(rowWith(100), 'v', { $gte: 10, $lte: 100 }, () => {})).toBe(true); // inclusive upper
  });

  it('excludes rows outside the bounds', () => {
    expect(numberRange(rowWith(5), 'v', { $gte: 10 }, () => {})).toBe(false);
    expect(numberRange(rowWith(200), 'v', { $lte: 100 }, () => {})).toBe(false);
  });

  it('treats a missing bound as open-ended', () => {
    expect(numberRange(rowWith(9999), 'v', { $gte: 10 }, () => {})).toBe(true);
    expect(numberRange(rowWith(-5), 'v', { $lte: 100 }, () => {})).toBe(true);
  });

  it('excludes non-numeric row values', () => {
    expect(numberRange(rowWith(undefined), 'v', { $gte: 10 }, () => {})).toBe(false);
    expect(numberRange(rowWith('50'), 'v', { $gte: 10 }, () => {})).toBe(false);
  });

  // The crux of the bug: TanStack auto-removes a column filter when `filterFn.autoRemove(value)`
  // returns true. The built-in `inNumberRange.autoRemove` reads `value[0]`/`value[1]` and so
  // treats our `{ $gte, $lte }` object as empty, silently dropping the filter. Our autoRemove must
  // keep any range with at least one bound and only clear when both are absent.
  describe('autoRemove', () => {
    const autoRemove = numberRange.autoRemove!;

    it('does NOT remove a range with either bound set', () => {
      expect(autoRemove({ $gte: 10 }, undefined as never)).toBe(false);
      expect(autoRemove({ $lte: 100 }, undefined as never)).toBe(false);
      expect(autoRemove({ $gte: 10, $lte: 100 }, undefined as never)).toBe(false);
      expect(autoRemove({ $gte: 0 }, undefined as never)).toBe(false); // zero is a valid bound
    });

    it('removes when the value is empty or absent', () => {
      expect(autoRemove(undefined, undefined as never)).toBe(true);
      expect(autoRemove({}, undefined as never)).toBe(true);
    });
  });
});
