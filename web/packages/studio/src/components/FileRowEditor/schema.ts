// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_ID_KEY,
  type DataFileColumn,
  type DataFileColumnType,
  type DataFileRow,
} from '@studio/components/FileRowEditor/types';

/** How many rows to sample when inferring the schema. */
const DEFAULT_SAMPLE_SIZE = 100;
/** String columns whose sampled values exceed this length get a multi-line editor. */
const MULTILINE_LENGTH = 80;
/** A string/boolean column is treated as an enum when its distinct count is in this range. */
const MIN_ENUM_OPTIONS = 2;
const MAX_ENUM_OPTIONS = 8;

/**
 * Infers a single column's logical type from a set of sampled values. Nulls/undefined
 * are ignored; an all-null column is `'null'`. Any object/array value makes the column
 * `'json'`. Mixed primitive kinds collapse to `'string'` (rendered as text).
 */
export const inferColumnType = (values: unknown[]): DataFileColumnType => {
  let sawValue = false;
  let sawString = false;
  let sawBoolean = false;
  let sawNumber = false;
  let sawFloat = false;

  for (const value of values) {
    if (value === null || value === undefined) {
      continue;
    }
    sawValue = true;
    if (typeof value === 'object') {
      return 'json';
    }
    if (typeof value === 'boolean') {
      sawBoolean = true;
      continue;
    }
    if (typeof value === 'number') {
      sawNumber = true;
      if (!Number.isInteger(value)) {
        sawFloat = true;
      }
      continue;
    }
    // strings, bigint, symbol — render as text
    sawString = true;
  }

  if (!sawValue) {
    return 'null';
  }
  const distinctKinds = Number(sawString) + Number(sawBoolean) + Number(sawNumber);
  if (distinctKinds > 1) {
    return 'string';
  }
  if (sawBoolean) {
    return 'boolean';
  }
  if (sawNumber) {
    return sawFloat ? 'float' : 'int';
  }
  return 'string';
};

/**
 * Derives the ordered column schema from row-like data by sampling values. Columns
 * appear in first-seen key order across the sample so a sparse first row doesn't hide
 * fields. The reserved {@link ROW_ID_KEY} is never surfaced as a column.
 */
export const inferColumns = (
  rows: DataFileRow[],
  sampleSize: number = DEFAULT_SAMPLE_SIZE
): DataFileColumn[] => {
  const sample = rows.slice(0, sampleSize);

  const keys: string[] = [];
  const seen = new Set<string>();
  for (const row of sample) {
    for (const key of Object.keys(row)) {
      if (key === ROW_ID_KEY || seen.has(key)) {
        continue;
      }
      seen.add(key);
      keys.push(key);
    }
  }

  return keys.map((key) => {
    const values = sample.map((row) => row[key]);
    const present = values.filter((value) => value !== null && value !== undefined);
    const type = inferColumnType(values);

    const multiline =
      type === 'string' &&
      present.some((value) => typeof value === 'string' && value.length > MULTILINE_LENGTH);

    const distinct =
      (type === 'string' || type === 'boolean') && !multiline
        ? Array.from(new Set(present.map((value) => String(value)))).sort()
        : [];
    const options =
      distinct.length >= MIN_ENUM_OPTIONS && distinct.length <= MAX_ENUM_OPTIONS
        ? distinct
        : undefined;

    return { key, label: key, type, editable: true, multiline, options };
  });
};

/** Formats a value for display in a table cell, by logical type. */
export const formatCellValue = (value: unknown, type: DataFileColumnType): string => {
  if (value === null || value === undefined) {
    return '';
  }
  if (type === 'json') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
};

/** A sensible empty value for a freshly-added row's column, by logical type. */
export const defaultValueForType = (type: DataFileColumnType): unknown => {
  switch (type) {
    case 'int':
    case 'float':
      return 0;
    case 'boolean':
      return false;
    case 'json':
      return {};
    case 'null':
      return null;
    default:
      return '';
  }
};

/** Total-ordering comparator that tolerates null/undefined and mixed scalar types. */
export const compareValues = (a: unknown, b: unknown): number => {
  if (a === b) {
    return 0;
  }
  if (a === null || a === undefined) {
    return -1;
  }
  if (b === null || b === undefined) {
    return 1;
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  if (typeof a === 'boolean' && typeof b === 'boolean') {
    return a === b ? 0 : a ? 1 : -1;
  }
  return String(a).localeCompare(String(b));
};
