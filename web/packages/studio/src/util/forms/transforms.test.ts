// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatWhitespaceHyphens, transformStrOrNum } from '@studio/util/forms/transforms';
import type { ChangeEvent } from 'react';

describe('transformStrOrNum', () => {
  it('returns a number for integer strings', () => {
    expect(transformStrOrNum('42')).toBe(42);
    expect(typeof transformStrOrNum('42')).toBe('number');
  });

  it('returns a number for decimal strings (parseInt truncates)', () => {
    expect(transformStrOrNum('3.14')).toBe(3);
    expect(typeof transformStrOrNum('3.14')).toBe('number');
  });

  it('returns the string for non-numeric strings', () => {
    expect(transformStrOrNum('hello')).toBe('hello');
    expect(typeof transformStrOrNum('hello')).toBe('string');
  });

  it('returns the string for empty string', () => {
    expect(transformStrOrNum('')).toBe('');
    expect(typeof transformStrOrNum('')).toBe('string');
  });

  it('returns the string for mixed alphanumeric input', () => {
    expect(transformStrOrNum('12abc')).toBe('12abc');
  });

  it('returns a number for zero', () => {
    expect(transformStrOrNum('0')).toBe(0);
    expect(typeof transformStrOrNum('0')).toBe('number');
  });
});

describe('formatWhitespaceHyphens', () => {
  it('normalizes strings', () => {
    expect(formatWhitespaceHyphens('hello world')).toBe('hello-world');
    expect(formatWhitespaceHyphens('a--b')).toBe('a-b');
    expect(formatWhitespaceHyphens('  x  ')).toBe('x-');
  });

  it('strips leading hyphens', () => {
    expect(formatWhitespaceHyphens('-foo')).toBe('foo');
    expect(formatWhitespaceHyphens('- foo -')).toBe('foo-');
  });

  it('preserves trailing separators while typing', () => {
    expect(formatWhitespaceHyphens('foo ')).toBe('foo-');
    expect(formatWhitespaceHyphens('foo-')).toBe('foo-');
  });

  it('can strip trailing hyphens for finalized values', () => {
    expect(formatWhitespaceHyphens('foo-', { stripTrailing: true })).toBe('foo');
    expect(formatWhitespaceHyphens('- foo -', { stripTrailing: true })).toBe('foo');
  });

  it('reads value from a change event', () => {
    const event = {
      target: { value: 'foo  bar' },
    } as ChangeEvent<HTMLInputElement>;
    expect(formatWhitespaceHyphens(event)).toBe('foo-bar');
  });

  it('prefers currentTarget over target for change events', () => {
    const event = {
      currentTarget: { value: 'foo  bar' },
      target: { value: 'wrong' },
    } as ChangeEvent<HTMLInputElement>;
    expect(formatWhitespaceHyphens(event)).toBe('foo-bar');
  });
});
