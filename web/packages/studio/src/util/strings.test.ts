// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { capitalize, formatKeyLabel, getTextWithCount, parseCSV } from '@studio/util/strings';

describe('#getTextWithCount', () => {
  it('should return the correct text with count using default suffix', () => {
    expect(getTextWithCount('test', 0)).toBe('0 tests');
    expect(getTextWithCount('test', 1)).toBe('1 test');
    expect(getTextWithCount('test', 2)).toBe('2 tests');
  });

  it('should return the correct text with count using plural', () => {
    expect(getTextWithCount('entry', 0, 'entries')).toBe('0 entries');
    expect(getTextWithCount('entry', 1, 'entries')).toBe('1 entry');
    expect(getTextWithCount('entry', 2, 'entries')).toBe('2 entries');
  });
});

describe('#formatKeyLabel', () => {
  it.each([
    ['prompt_tokens', 'Prompt Tokens'],
    ['top_p', 'Top P'],
    ['m_temperature', 'M Temperature'],
    ['model', 'Model'],
    ['createdBy', 'CreatedBy'],
    ['index-point', 'Index-point'],
    ['', ''],
  ])('formats "%s" as "%s"', (input, expected) => {
    expect(formatKeyLabel(input)).toBe(expected);
  });
});

describe('#capitalize', () => {
  it('should capitalize the first letter of a string', () => {
    expect(capitalize('hello')).toBe('Hello');
    expect(capitalize('world')).toBe('World');
  });

  it('should handle single character strings', () => {
    expect(capitalize('a')).toBe('A');
  });

  it('should handle empty strings', () => {
    expect(capitalize('')).toBe('');
  });

  it('should not change already capitalized strings', () => {
    expect(capitalize('Hello')).toBe('Hello');
  });
});

describe('#parseCSV', () => {
  it('should parse a valid CSV string with headers', () => {
    const csvString = 'name,age\nAlice,30\nBob,25';
    const result = parseCSV({ csvString, options: { header: true } });
    expect(result).toEqual([
      { name: 'Alice', age: '30' },
      { name: 'Bob', age: '25' },
    ]);
  });

  it('should return empty array and log errors on invalid CSV', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    // Unmatched quotes cause a parse error in PapaParse
    const csvString = '"unclosed quote';
    const result = parseCSV({ csvString, options: { header: true } });
    expect(result).toEqual([]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
