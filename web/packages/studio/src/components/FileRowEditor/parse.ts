// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataFileRow } from '@studio/components/FileRowEditor/types';

/** Data file formats recognized by {@link formatFromFileName}. */
export type DataFileFormat = 'json' | 'jsonl' | 'csv' | 'parquet' | 'unknown';

/** Formats that {@link parseDataFile} can parse from in-browser text content. */
export const TEXT_PARSEABLE_FORMATS: readonly DataFileFormat[] = ['json', 'jsonl', 'csv'];

/** Derives a data file format from a file name's extension. */
export const formatFromFileName = (fileName: string): DataFileFormat => {
  const extension = fileName.split('.').pop()?.toLowerCase();
  switch (extension) {
    case 'json':
      return 'json';
    case 'jsonl':
    case 'ndjson':
      return 'jsonl';
    case 'csv':
      return 'csv';
    case 'parquet':
    case 'pq':
      return 'parquet';
    default:
      return 'unknown';
  }
};

/**
 * Normalizes an arbitrary parsed value into a row object. Plain objects pass through;
 * arrays and primitives are wrapped as `{ value }` so any JSON-array file still renders.
 */
const normalizeRow = (value: unknown): DataFileRow =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as DataFileRow)
    : { value };

const parseJson = (content: string): DataFileRow[] => {
  const data: unknown = JSON.parse(content);
  const list = Array.isArray(data) ? data : [data];
  return list.map(normalizeRow);
};

const parseJsonl = (content: string): DataFileRow[] =>
  content
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => normalizeRow(JSON.parse(line)));

/**
 * Parses CSV text into a grid of string cells, honoring RFC-4180 quoting: quoted
 * fields may contain commas and newlines, and `""` is an escaped quote.
 */
const parseCsvGrid = (content: string): string[][] => {
  const rows: string[][] = [];
  let field = '';
  let row: string[] = [];
  let inQuotes = false;

  for (let i = 0; i < content.length; i++) {
    const char = content[i];
    if (inQuotes) {
      if (char === '"') {
        if (content[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && content[i + 1] === '\n') {
        i++;
      }
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
    } else {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  // Drop blank trailing lines (a single empty cell).
  return rows.filter((cells) => cells.length > 1 || cells[0] !== '');
};

/** Coerces a raw CSV string cell into a boolean/number when it unambiguously is one. */
const coerceScalar = (raw: string): unknown => {
  if (raw === '') {
    return '';
  }
  if (raw === 'true') {
    return true;
  }
  if (raw === 'false') {
    return false;
  }
  if (/^-?\d+$/.test(raw)) {
    const value = Number(raw);
    if (Number.isSafeInteger(value)) {
      return value;
    }
  }
  if (/^-?\d*\.\d+$/.test(raw)) {
    return Number(raw);
  }
  return raw;
};

const parseCsv = (content: string): DataFileRow[] => {
  const grid = parseCsvGrid(content);
  if (grid.length === 0) {
    return [];
  }
  const [header, ...body] = grid;
  return body.map((cells) => {
    const row: DataFileRow = {};
    header.forEach((key, index) => {
      row[key] = coerceScalar(cells[index] ?? '');
    });
    return row;
  });
};

/**
 * Parses the text content of a data file into row-like records. Supports JSON (array
 * or single object), JSONL/NDJSON, and CSV. Binary formats (e.g. Parquet) are not
 * parseable in-browser and must be loaded through the Files API. Throws on malformed
 * input or an unsupported format.
 */
export const parseDataFile = (content: string, format: DataFileFormat): DataFileRow[] => {
  switch (format) {
    case 'json':
      return parseJson(content);
    case 'jsonl':
      return parseJsonl(content);
    case 'csv':
      return parseCsv(content);
    default:
      throw new Error(`Unsupported data file format: ${format}`);
  }
};
