// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { OutputFormat } from '@studio/components/transform/formats';

/** A single row of the custom format's key/template grid. */
export interface CustomTemplateRow {
  readonly key: string;
  readonly value: string;
}

/** Segments that would reach Object.prototype, so a key can never pollute it. */
const UNSAFE_SEGMENTS = new Set(['__proto__', 'constructor', 'prototype']);

/**
 * Writes `value` at a dot path inside `target`, creating containers as it goes.
 * A numeric segment creates (or extends) an array, so `messages.0.content`
 * yields `{ messages: [{ content: value }] }`. Paths that traverse a prototype
 * are dropped whole — the template is user-authored and is also applied to rows
 * in the browser for the preview.
 */
export const setAtPath = (
  target: Record<string, unknown>,
  path: string,
  value: unknown
): Record<string, unknown> => {
  const segments = path.split('.').filter(Boolean);
  if (segments.length === 0 || segments.some((segment) => UNSAFE_SEGMENTS.has(segment))) {
    return target;
  }

  let cursor: Record<string, unknown> | unknown[] = target;
  for (let index = 0; index < segments.length - 1; index += 1) {
    const segment = segments[index];
    const nextIsIndex = /^\d+$/.test(segments[index + 1]);
    const existing = readSegment(cursor, segment);
    const container =
      isContainer(existing) && Array.isArray(existing) === nextIsIndex
        ? existing
        : nextIsIndex
          ? []
          : {};
    writeSegment(cursor, segment, container);
    cursor = container;
  }

  writeSegment(cursor, segments[segments.length - 1], value);
  return target;
};

const isContainer = (value: unknown): value is Record<string, unknown> | unknown[] =>
  typeof value === 'object' && value !== null;

const readSegment = (cursor: Record<string, unknown> | unknown[], segment: string): unknown =>
  Array.isArray(cursor) ? cursor[Number(segment)] : cursor[segment];

const writeSegment = (
  cursor: Record<string, unknown> | unknown[],
  segment: string,
  value: unknown
): void => {
  if (Array.isArray(cursor)) {
    cursor[Number(segment)] = value;
  } else {
    cursor[segment] = value;
  }
};

/**
 * Builds the `schema_transform` template. Preset fields are written at their dot
 * paths in declaration order, then the format's constants, so a literal (like a
 * chat role) can never be clobbered by a mapping. Blank mappings are skipped —
 * an unmapped optional field simply does not appear in the output.
 */
export const buildTemplate = (
  format: OutputFormat,
  mappings: Readonly<Record<string, string>>,
  customRows: readonly CustomTemplateRow[]
): Record<string, unknown> => {
  const template: Record<string, unknown> = {};

  for (const field of format.fields) {
    const value = mappings[field.path]?.trim();
    if (value) {
      setAtPath(template, field.path, value);
    }
  }

  for (const [path, value] of Object.entries(format.constants ?? {})) {
    setAtPath(template, path, value);
  }

  for (const row of customRows) {
    const key = row.key.trim();
    if (key) {
      setAtPath(template, key, row.value.trim());
    }
  }

  return template;
};

/** Wraps a source column name as the Jinja2 reference the processor expects. */
export const columnReference = (column: string): string => `{{ ${column} }}`;

/** Preferred name for the identifier column the transform job generates. */
const GENERATED_ID_BASE = 'row_id';

/**
 * Name for the generated identifier column. Data Designer rejects a declared
 * column whose name collides with a seed column, so suffix until it is free.
 */
export const resolveGeneratedIdColumn = (columns: readonly string[]): string => {
  const taken = new Set(columns);
  if (!taken.has(GENERATED_ID_BASE)) {
    return GENERATED_ID_BASE;
  }
  let suffix = 2;
  while (taken.has(`${GENERATED_ID_BASE}_${suffix}`)) {
    suffix += 1;
  }
  return `${GENERATED_ID_BASE}_${suffix}`;
};

/**
 * Guesses a mapping for each field from the source columns: an exact hint match
 * wins over a substring match, and earlier hints win over later ones. Columns
 * are never reused, so two fields cannot both claim `response`.
 *
 * An identity field with no match falls back to `generatedIdColumn`, which the
 * job creates as a UUID sampler rather than reading from the source.
 */
export const autoMapFields = (
  format: OutputFormat,
  columns: readonly string[],
  generatedIdColumn?: string
): Record<string, string> => {
  const claimed = new Set<string>();
  const mappings: Record<string, string> = {};

  for (const field of format.fields) {
    const match = findColumnMatch(field.hints, columns, claimed);
    if (match) {
      claimed.add(match);
      mappings[field.path] = columnReference(match);
    } else if (field.identity && generatedIdColumn) {
      mappings[field.path] = columnReference(generatedIdColumn);
    }
  }

  return mappings;
};

/** Root variable names referenced by any template value, e.g. `{{ a.b | upper }}` → `a`. */
export const templateReferences = (template: Record<string, unknown>): Set<string> => {
  const found = new Set<string>();
  const visit = (value: unknown): void => {
    if (typeof value === 'string') {
      for (const match of value.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)/g)) {
        found.add(match[1]);
      }
    } else if (Array.isArray(value)) {
      value.forEach(visit);
    } else if (typeof value === 'object' && value !== null) {
      Object.values(value).forEach(visit);
    }
  };
  visit(template);
  return found;
};

/**
 * Whether the finished template actually uses the generated identifier. Checked
 * against the rendered template rather than the mapping state so that clearing
 * or overwriting the field also drops the column from the job.
 */
export const usesGeneratedIdColumn = (
  template: Record<string, unknown>,
  generatedIdColumn: string,
  columns: readonly string[]
): boolean =>
  !columns.includes(generatedIdColumn) && templateReferences(template).has(generatedIdColumn);

/**
 * Splits a column name into words, treating `_`, `-` and camelCase humps as
 * boundaries: `userRequest` and `user_request` both become `['user', 'request']`.
 */
const tokenize = (column: string): string[] =>
  column
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);

/**
 * Matches on whole words rather than substrings. A plain `includes` lets a short
 * hint swallow an unrelated column — `id` matches `ideal_response` — which is
 * worse than no guess, since a wrong auto-map looks deliberate.
 */
const findColumnMatch = (
  hints: readonly string[],
  columns: readonly string[],
  claimed: ReadonlySet<string>
): string | undefined => {
  const available = columns
    .filter((column) => !claimed.has(column))
    .map((column) => ({ column, tokens: tokenize(column) }));

  for (const hint of hints) {
    const exact = available.find(({ tokens }) => tokens.join('_') === hint);
    if (exact) {
      return exact.column;
    }
  }
  for (const hint of hints) {
    const word = available.find(({ tokens }) => tokens.includes(hint));
    if (word) {
      return word.column;
    }
  }
  return undefined;
};

/** Paths of required fields that have no template yet. */
export const missingRequiredPaths = (
  format: OutputFormat,
  mappings: Readonly<Record<string, string>>
): string[] =>
  format.fields
    .filter((field) => field.required && !mappings[field.path]?.trim())
    .map((field) => field.path);
