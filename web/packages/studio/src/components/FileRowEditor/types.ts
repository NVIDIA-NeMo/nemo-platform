// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Reserved key holding a stable per-row identity. It is assigned when rows are
 * loaded, is never shown as a column, and is never edited. Using a synthetic key
 * (rather than a `id` field that may or may not exist on the source data) lets the
 * editor track, duplicate, and delete rows of any shape.
 */
export const ROW_ID_KEY = '__rowId';

/**
 * Logical column data types inferred from a column's sampled values. These drive the
 * cell glyph, the schema/type tag, and which editor control is rendered.
 */
export type DataFileColumnType = 'int' | 'float' | 'string' | 'boolean' | 'json' | 'null';

export interface DataFileColumn {
  /** Property key on a {@link DataFileRow}. */
  key: string;
  /** Human-readable header label. Defaults to {@link key} when inferred. */
  label: string;
  /** Logical type used for the schema chip / glyph and the editor field tag. */
  type: DataFileColumnType;
  /** Whether the value is editable in the row editor. Defaults to true. */
  editable?: boolean;
  /** Render the editor control as a multi-line text area (set for long string values). */
  multiline?: boolean;
  /**
   * The allowed values for an enum-like column. When present, the editor renders a
   * single-select dropdown (instead of a free-text input) and the table exposes a
   * single-select filter. Inferred for low-cardinality string/boolean columns, and can
   * be supplied explicitly via the `columns` prop.
   */
  options?: string[];
}

/**
 * A single record in the data file. Arbitrary, row-like shape (the keys come from the
 * file's schema). Rows additionally carry a reserved {@link ROW_ID_KEY} for identity.
 */
export type DataFileRow = Record<string, unknown>;
