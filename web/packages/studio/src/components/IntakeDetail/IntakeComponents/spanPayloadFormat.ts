// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { type Edit, format } from 'jsonc-parser';

export type SpanPayloadFormat = 'raw' | 'md' | 'json';

export interface SpanPayloadFormatState {
  format: SpanPayloadFormat;
  select: (format: SpanPayloadFormat) => void;
  isJson: boolean;
  isEmpty: boolean;
}

const JSON_INDENT_OPTIONS = { tabSize: 2, insertSpaces: true, eol: '\n' };

// Not jsonc-parser's applyEdits: it rebuilds the document per edit, so a 585KB
// payload takes ~6s there against ~3ms here.
const applyEdits = (text: string, edits: Edit[]): string => {
  const parts: string[] = [];
  let cursor = 0;
  for (const edit of [...edits].sort((a, b) => a.offset - b.offset)) {
    parts.push(text.slice(cursor, edit.offset), edit.content);
    cursor = edit.offset + edit.length;
  }
  parts.push(text.slice(cursor));
  return parts.join('');
};

/** Whether a JSON view applies, without paying to build one. */
export const isJsonPayload = (value: string | null | undefined): boolean =>
  jsonSource(value) !== null;

const jsonSource = (value: string | null | undefined): string | null => {
  const trimmed = value?.trim();
  if (!trimmed || !(trimmed.startsWith('{') || trimmed.startsWith('['))) {
    return null;
  }
  try {
    // Validity gate only; the result is discarded. Re-indenting the source is
    // what keeps the view lossless — a JSON.stringify(JSON.parse(...)) round
    // trip reformats every number through a float64 and drops duplicate keys.
    JSON.parse(trimmed);
    return trimmed;
  } catch {
    return null;
  }
};

/** Re-indented `value` when it is a JSON object or array, else `null`. */
export const parseJsonPayload = (value: string | null | undefined): string | null => {
  const source = jsonSource(value);
  return source === null
    ? null
    : applyEdits(source, format(source, undefined, JSON_INDENT_OPTIONS));
};

export const autoFormat = (isJson: boolean): SpanPayloadFormat => (isJson ? 'json' : 'raw');
