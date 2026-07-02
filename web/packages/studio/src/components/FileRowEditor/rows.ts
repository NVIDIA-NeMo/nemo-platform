// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { compareValues, defaultValueForType } from '@studio/components/FileRowEditor/schema';
import {
  ROW_ID_KEY,
  type DataFileColumn,
  type DataFileRow,
} from '@studio/components/FileRowEditor/types';

/** Reads a row's stable identity. */
export const rowId = (row: DataFileRow): number => row[ROW_ID_KEY] as number;

/** Assigns stable, sequential identities to freshly-loaded rows. */
export const assignRowIds = (rows: DataFileRow[]): DataFileRow[] =>
  rows.map((row, index) => ({ ...row, [ROW_ID_KEY]: index + 1 }));

export const cloneRow = (row: DataFileRow): DataFileRow => {
  try {
    return structuredClone(row);
  } catch {
    return JSON.parse(JSON.stringify(row)) as DataFileRow;
  }
};

export const nextId = (rows: DataFileRow[]): number =>
  rows.reduce((max, row) => Math.max(max, rowId(row) || 0), 0) + 1;

/** Builds a blank row from the schema, with type-appropriate empty values. */
export const emptyRow = (id: number, columns: DataFileColumn[]): DataFileRow => {
  const row: DataFileRow = { [ROW_ID_KEY]: id };
  for (const column of columns) {
    // Enum columns start on their first allowed value so the select isn't blank.
    row[column.key] =
      column.type === 'string' && column.options?.length
        ? column.options[0]
        : defaultValueForType(column.type);
  }
  return row;
};

/**
 * StudioDataView runs in `manual` mode (manual filtering/sorting/pagination), so the
 * consumer must derive the page slice itself. This applies the data view's search,
 * column filters, and sorting to in-memory rows — generically, across whatever columns
 * the data happens to have.
 */
export const deriveRows = (
  rows: DataFileRow[],
  {
    search,
    columnFilters,
    sorting,
  }: {
    search: string;
    columnFilters: { id: string; value: unknown }[];
    sorting: { id: string; desc: boolean }[];
  }
): DataFileRow[] => {
  let result = rows;

  const query = search.trim().toLowerCase();
  if (query) {
    result = result.filter((row) =>
      Object.keys(row).some(
        (key) =>
          key !== ROW_ID_KEY &&
          String(row[key] ?? '')
            .toLowerCase()
            .includes(query)
      )
    );
  }

  for (const { id, value } of columnFilters) {
    if (value === undefined || value === null || value === '') {
      continue;
    }
    result = result.filter((row) => String(row[id] ?? '') === String(value));
  }

  if (sorting.length > 0) {
    const { id, desc } = sorting[0];
    result = [...result].sort((a, b) => {
      const cmp = compareValues(a[id], b[id]);
      return desc ? -cmp : cmp;
    });
  }

  return result;
};

/** Formats a byte count as a human-readable file-size label (e.g. `1.2 MB`). */
export const formatBytes = (bytes: number): string => {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
};
