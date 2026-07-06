// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { NumberRangeFilterValue } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import type { MultiState } from '@nemo/common/src/components/DataView/internal/types';
import { rankItem } from '@tanstack/match-sorter-utils';
import type { FilterFn, FilterMeta, Row } from '@tanstack/react-table';

/**
 * Supplemental filter functions for the DataView component. These are custom filter functions
 * that can be used in the `filterFn` or `globalFilterFn` props.
 */
export const filterFunctions = {
  /**
   * Fuzzy filter — approximately matches the text entered to the data in the column.
   * @see https://tanstack.com/table/latest/docs/guide/fuzzy-filtering#defining-a-custom-fuzzy-filter-function
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic across data types
  fuzzy: (row: Row<any>, columnId: string, value: any, addMeta: (meta: FilterMeta) => void) => {
    const itemRank = rankItem(row.getValue(columnId), value);
    addMeta({ itemRank });
    return itemRank.passed;
  },
  /** @deprecated Use `includesString` instead. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic across data types
  singleSelect: (row: Row<any>, columnId: string, value: string | undefined) => {
    const rowValue = `${row.getValue(columnId)}`.toLowerCase();
    return rowValue === value?.toLowerCase();
  },
  /** Case insensitive multi-select filter. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic across data types
  multiSelect: (row: Row<any>, columnId: string, value: MultiState | undefined) => {
    const rowValue = `${row.getValue(columnId)}`;
    return Object.keys(value ?? {}).some((v) => v.toLowerCase() === rowValue.toLowerCase());
  },
  /** Case sensitive multi-select filter. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic across data types
  multiSelectSensitive: (row: Row<any>, columnId: string, value: MultiState | undefined) => {
    const rowValue = `${row.getValue(columnId)}`;
    return Object.keys(value ?? {}).some((v) => v === rowValue);
  },
  /**
   * Numeric range filter for `{ $gte, $lte }` values. Keeps rows whose numeric value falls
   * within the inclusive bounds; either bound may be omitted for an open-ended range.
   *
   * An explicit `autoRemove` is essential: without a `filterFn`, TanStack resolves a numeric
   * column to its built-in `inNumberRange`, whose `autoRemove` reads the value as a `[min, max]`
   * tuple and treats our `{ $gte, $lte }` object as empty — silently dropping the filter on every
   * `setFilterValue`. This keeps a filter with either bound set and only clears it when both are
   * absent (matching the control, which emits `undefined` to clear).
   */
  numberRange: Object.assign(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic across data types
    (row: Row<any>, columnId: string, value: NumberRangeFilterValue | undefined) => {
      const rowValue = row.getValue(columnId);
      if (typeof rowValue !== 'number' || Number.isNaN(rowValue)) return false;
      const { $gte, $lte } = value ?? {};
      if ($gte != null && rowValue < $gte) return false;
      if ($lte != null && rowValue > $lte) return false;
      return true;
    },
    {
      autoRemove: (value: NumberRangeFilterValue | undefined) =>
        value == null || (value.$gte == null && value.$lte == null),
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- FilterFn generic is data-type agnostic here
  ) as FilterFn<any>,
};
