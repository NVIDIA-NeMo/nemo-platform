// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getAriaSort } from './a11y';

describe('#getAriaSort', () => {
  describe('when sortBy matches targetSortBy', () => {
    it('returns "ascending" when order is "asc"', () => {
      const result = getAriaSort('name', 'name', 'asc');
      expect(result).toBe('ascending');
    });

    it('returns "descending" when order is "desc"', () => {
      const result = getAriaSort('name', 'name', 'desc');
      expect(result).toBe('descending');
    });
  });

  describe('when sortBy does not match targetSortBy', () => {
    it('returns undefined when different sort fields', () => {
      const result = getAriaSort('name', 'date', 'asc');
      expect(result).toBeUndefined();
    });

    it('returns undefined regardless of order when fields differ', () => {
      const resultAsc = getAriaSort('name', 'date', 'asc');
      const resultDesc = getAriaSort('name', 'date', 'desc');

      expect(resultAsc).toBeUndefined();
      expect(resultDesc).toBeUndefined();
    });
  });

  describe('edge cases', () => {
    it('handles empty strings correctly', () => {
      const result = getAriaSort('', '', 'asc');
      expect(result).toBe('ascending');
    });

    it('is case sensitive for field names', () => {
      const result = getAriaSort('Name', 'name', 'asc');
      expect(result).toBeUndefined();
    });

    it('handles special characters in field names', () => {
      const fieldName = 'field-with_special.chars';
      const result = getAriaSort(fieldName, fieldName, 'desc');
      expect(result).toBe('descending');
    });
  });

  describe('parameterized tests', () => {
    it.each([
      ['name', 'name', 'asc', 'ascending'],
      ['name', 'name', 'desc', 'descending'],
      ['date', 'date', 'asc', 'ascending'],
      ['date', 'date', 'desc', 'descending'],
      ['name', 'date', 'asc', undefined],
      ['name', 'date', 'desc', undefined],
      ['', 'name', 'asc', undefined],
      ['name', '', 'asc', undefined],
    ] as const)(
      'getAriaSort("%s", "%s", "%s") returns %s',
      (sortBy, targetSortBy, order, expected) => {
        const result = getAriaSort(sortBy, targetSortBy, order);
        expect(result).toBe(expected);
      }
    );
  });
});
