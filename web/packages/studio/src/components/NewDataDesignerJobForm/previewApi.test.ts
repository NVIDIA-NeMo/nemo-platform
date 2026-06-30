// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  formatPreviewLogsForDisplay,
  isAbortError,
} from '@studio/components/NewDataDesignerJobForm/previewApi';

describe('formatPreviewLogsForDisplay', () => {
  it('returns empty-ish input as-is', () => {
    expect(formatPreviewLogsForDisplay('')).toBe('');
    expect(formatPreviewLogsForDisplay('  ')).toBe('  ');
  });

  it('pretty-prints JSON object lines', () => {
    const input = '{"key":"value"}';
    const result = formatPreviewLogsForDisplay(input);
    expect(result).toContain('"key": "value"');
    expect(result).toContain('\n'); // indented
  });

  it('pretty-prints JSON array lines', () => {
    const input = '[1,2,3]';
    const result = formatPreviewLogsForDisplay(input);
    expect(result).toContain('[\n');
  });

  it('passes through non-JSON lines unchanged', () => {
    const input = 'plain text line';
    expect(formatPreviewLogsForDisplay(input)).toBe('plain text line');
  });

  it('handles mixed lines', () => {
    const input = 'hello\n{"a":1}\nworld';
    const result = formatPreviewLogsForDisplay(input);
    const lines = result.split('\n');
    expect(lines[0]).toBe('hello');
    expect(lines[lines.length - 1]).toBe('world');
    expect(result).toContain('"a": 1');
  });

  it('handles invalid JSON that looks like JSON', () => {
    const input = '{broken json}';
    expect(formatPreviewLogsForDisplay(input)).toBe('{broken json}');
  });
});

describe('isAbortError', () => {
  it('returns true for AbortError', () => {
    const err = new DOMException('aborted', 'AbortError');
    expect(isAbortError(err)).toBe(true);
  });

  it('returns false for other errors', () => {
    expect(isAbortError(new Error('oops'))).toBe(false);
  });

  it('returns false for non-objects', () => {
    expect(isAbortError(null)).toBe(false);
    expect(isAbortError('string')).toBe(false);
    expect(isAbortError(undefined)).toBe(false);
  });
});
