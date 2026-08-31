// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Row } from '@studio/util/files';
import Handlebars from 'handlebars';

/** Matches a bare `{{ column }}`, `{{ nested.path }}`, or either with Jinja2 filters. */
const SIMPLE_REFERENCE = /\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(\|[^}]*)?\}\}/g;

export interface RenderedTemplate {
  row: Row;
  /**
   * True when part of a value could not be rendered faithfully — a Jinja2 filter
   * was dropped, or the template used a construct only Handlebars understands.
   * Data Designer transforms run server-side, so the browser can only
   * approximate anything beyond a plain reference.
   */
  approximated: boolean;
}

/**
 * Reads a dot path out of a row: `reference.expected` and `messages.0.content`
 * both resolve, so a source column holding an object or array is reachable.
 */
const resolvePath = (row: Row, path: string): unknown => {
  let cursor: unknown = row;
  for (const segment of path.split('.')) {
    if (cursor === null || typeof cursor !== 'object') {
      return undefined;
    }
    cursor = Array.isArray(cursor)
      ? cursor[Number(segment)]
      : (cursor as Record<string, unknown>)[segment];
  }
  return cursor;
};

/** A resolved value as template text. Objects and arrays become their JSON. */
const asText = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
};

/** Values for the Handlebars fallback, where a container has to be pre-rendered. */
const flattenRow = (row: Row): Row =>
  Object.fromEntries(
    Object.entries(row).map(([key, value]) => [
      key,
      typeof value === 'object' && value !== null ? JSON.stringify(value) : value,
    ])
  );

const parseIfJson = (value: string): unknown => {
  const trimmed = value.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      // Not JSON after all — keep the rendered text.
    }
  }
  return value;
};

/**
 * Renders one template value against a row.
 *
 * Plain references are resolved directly rather than handed to Handlebars: that
 * keeps dot paths working (Handlebars cannot see into a column it has already
 * been given as JSON text) and avoids HTML-escaping the result. Anything else —
 * a block, a helper — still falls back to Handlebars, and is flagged as
 * approximate since the real transform speaks Jinja2.
 */
const renderValue = (value: string, row: Row): { rendered: unknown; approximated: boolean } => {
  if (!value.includes('{{')) {
    return { rendered: value, approximated: false };
  }

  let approximated = false;
  const substituted = value.replace(SIMPLE_REFERENCE, (_match, path: string, filter?: string) => {
    if (filter) {
      approximated = true;
    }
    return asText(resolvePath(row, path));
  });

  // Braces left after removing every plain reference mean a block or a helper.
  const hasComplexConstruct = value.replace(SIMPLE_REFERENCE, '').includes('{{');
  if (!hasComplexConstruct) {
    return { rendered: parseIfJson(substituted), approximated };
  }

  try {
    return {
      rendered: parseIfJson(Handlebars.compile(value)(flattenRow(row))),
      approximated: true,
    };
  } catch {
    // An in-progress template (e.g. `{{name`) must not break the whole preview.
    return { rendered: value, approximated: true };
  }
};

/**
 * Applies a `schema_transform` template to one source row, preserving the
 * template's own shape: nested objects stay nested and numeric key segments
 * (already materialized as arrays by `setAtPath`) stay arrays.
 */
export const renderTemplate = (template: Record<string, unknown>, row: Row): RenderedTemplate => {
  let approximated = false;

  const visit = (value: unknown): unknown => {
    if (typeof value === 'string') {
      const result = renderValue(value, row);
      approximated = approximated || result.approximated;
      return result.rendered;
    }
    if (Array.isArray(value)) {
      return value.map(visit);
    }
    if (typeof value === 'object' && value !== null) {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, visit(entry)])
      );
    }
    return value;
  };

  return { row: visit(template) as Row, approximated };
};
