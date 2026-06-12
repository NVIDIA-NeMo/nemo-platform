// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildApiSearchParam, convertQueryToList, mergeURLSearchParams } from './search';

describe('buildApiSearchParam', () => {
  it('returns undefined for undefined input', () => {
    expect(buildApiSearchParam(undefined)).toBeUndefined();
  });

  it('returns undefined when no filterable values are present', () => {
    expect(buildApiSearchParam({})).toBeUndefined();
  });

  it('wraps string values with $like', () => {
    expect(buildApiSearchParam({ name: 'foo' })).toBe('{"name":{"$like":"foo"}}');
  });

  it('converts a full date range to $gte / $lte', () => {
    expect(buildApiSearchParam({ created_at: { start: '2024-01-01', end: '2024-12-31' } })).toBe(
      '{"created_at":{"$gte":"2024-01-01","$lte":"2024-12-31"}}'
    );
  });

  it('omits $lte when end is absent', () => {
    expect(buildApiSearchParam({ created_at: { start: '2024-01-01' } })).toBe(
      '{"created_at":{"$gte":"2024-01-01"}}'
    );
  });

  it('omits $gte when start is absent', () => {
    expect(buildApiSearchParam({ created_at: { end: '2024-12-31' } })).toBe(
      '{"created_at":{"$lte":"2024-12-31"}}'
    );
  });

  it('omits a date range field when both start and end are absent', () => {
    expect(buildApiSearchParam({ created_at: {} })).toBeUndefined();
  });

  it('combines string and date range fields', () => {
    const result = buildApiSearchParam({
      name: 'test',
      created_at: { start: '2024-01-01', end: '2024-12-31' },
    });
    expect(result).toBe(
      '{"name":{"$like":"test"},"created_at":{"$gte":"2024-01-01","$lte":"2024-12-31"}}'
    );
  });
});

describe('search utilities', () => {
  describe('mergeURLSearchParams', () => {
    it('should merge override values into base URLSearchParams', () => {
      const base = new URLSearchParams('?page=1&size=10');
      const overrides = { page: 2, filter: 'active' };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('2');
      expect(result.get('size')).toBe('10');
      expect(result.get('filter')).toBe('active');
    });

    it('should add new parameters from overrides', () => {
      const base = new URLSearchParams('?page=1');
      const overrides = { size: 20, sort: 'name' };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.get('size')).toBe('20');
      expect(result.get('sort')).toBe('name');
    });

    it('should delete parameters when override value is undefined', () => {
      const base = new URLSearchParams('?page=1&size=10&filter=active');
      const overrides = { filter: undefined };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.get('size')).toBe('10');
      expect(result.has('filter')).toBe(false);
    });

    it('should delete parameters when override value is empty string', () => {
      const base = new URLSearchParams('?page=1&size=10&filter=active');
      const overrides = { filter: '' };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.get('size')).toBe('10');
      expect(result.has('filter')).toBe(false);
    });

    it('should handle numeric values by converting to string', () => {
      const base = new URLSearchParams();
      const overrides = { page: 5, size: 100 };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('5');
      expect(result.get('size')).toBe('100');
    });

    it('should not delete parameters that do not exist in base when override is undefined', () => {
      const base = new URLSearchParams('?page=1');
      const overrides = { nonexistent: undefined };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.has('nonexistent')).toBe(false);
    });

    it('should handle empty base URLSearchParams', () => {
      const base = new URLSearchParams();
      const overrides = { page: 1, filter: 'test' };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.get('filter')).toBe('test');
    });

    it('should handle empty overrides object', () => {
      const base = new URLSearchParams('?page=1&size=10');
      const overrides = {};

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('1');
      expect(result.get('size')).toBe('10');
    });

    it('should not modify the original base URLSearchParams', () => {
      const base = new URLSearchParams('?page=1');
      const overrides = { page: 2 };

      mergeURLSearchParams(base, overrides);

      expect(base.get('page')).toBe('1'); // Original should be unchanged
    });

    it('should handle zero values correctly', () => {
      const base = new URLSearchParams('?page=1');
      const overrides = { page: 0, size: 0 };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('page')).toBe('0');
      expect(result.get('size')).toBe('0');
    });

    it('should handle boolean-like string values', () => {
      const base = new URLSearchParams();
      const overrides = { active: 'true', visible: 'false' };

      const result = mergeURLSearchParams(base, overrides);

      expect(result.get('active')).toBe('true');
      expect(result.get('visible')).toBe('false');
    });
  });

  describe('convertQueryToList', () => {
    it('should convert simple key-value pairs to list format', () => {
      const query = { page: 1, size: 10, filter: 'active' };

      const result = convertQueryToList(query);

      expect(result).toEqual(['page=1', 'size=10', 'filter=active']);
    });

    it('should handle undefined query by returning empty array', () => {
      const result = convertQueryToList(undefined);

      expect(result).toEqual([]);
    });

    it('should handle null query by returning empty array', () => {
      const result = convertQueryToList();

      expect(result).toEqual([]);
    });

    it('should handle empty object by returning empty array', () => {
      const query = {};

      const result = convertQueryToList(query);

      expect(result).toEqual([]);
    });

    it('should stringify object values', () => {
      const query = {
        filters: { status: 'active', type: 'user' },
        options: ['a', 'b', 'c'],
      };

      const result = convertQueryToList(query);

      expect(result).toEqual([
        'filters={"status":"active","type":"user"}',
        'options=["a","b","c"]',
      ]);
    });

    it('should handle null values by converting to empty string', () => {
      const query = { page: 1, filter: null };

      const result = convertQueryToList(query);

      expect(result).toEqual(['page=1', 'filter=']);
    });

    it('should handle undefined values by converting to empty string', () => {
      const query = { page: 1, filter: undefined };

      const result = convertQueryToList(query);

      expect(result).toEqual(['page=1', 'filter=']);
    });

    it('should handle boolean values', () => {
      const query = { active: true, visible: false };

      const result = convertQueryToList(query);

      expect(result).toEqual(['active=true', 'visible=false']);
    });

    it('should handle numeric values', () => {
      const query = { page: 1, size: 10, rating: 4.5 };

      const result = convertQueryToList(query);

      expect(result).toEqual(['page=1', 'size=10', 'rating=4.5']);
    });

    it('should handle string values', () => {
      const query = { search: 'hello world', category: 'tech' };

      const result = convertQueryToList(query);

      expect(result).toEqual(['search=hello world', 'category=tech']);
    });

    it('should handle mixed value types', () => {
      const query = {
        page: 1,
        active: true,
        filter: null,
        search: 'test',
        config: { theme: 'dark' },
      };

      const result = convertQueryToList(query);

      expect(result).toEqual([
        'page=1',
        'active=true',
        'filter=',
        'search=test',
        'config={"theme":"dark"}',
      ]);
    });

    it('should handle nested objects correctly', () => {
      const query = {
        user: {
          name: 'John',
          preferences: {
            theme: 'dark',
            language: 'en',
          },
        },
      };

      const result = convertQueryToList(query);

      expect(result).toEqual([
        'user={"name":"John","preferences":{"theme":"dark","language":"en"}}',
      ]);
    });

    it('should handle arrays of different types', () => {
      const query = {
        numbers: [1, 2, 3],
        strings: ['a', 'b', 'c'],
        mixed: [1, 'two', true, null],
      };

      const result = convertQueryToList(query);

      expect(result).toEqual([
        'numbers=[1,2,3]',
        'strings=["a","b","c"]',
        'mixed=[1,"two",true,null]',
      ]);
    });

    it('should handle zero and empty string values', () => {
      const query = { count: 0, message: '' };

      const result = convertQueryToList(query);

      expect(result).toEqual(['count=0', 'message=']);
    });

    it('should preserve order of object keys', () => {
      const query = { z: 1, a: 2, m: 3 };

      const result = convertQueryToList(query);

      // Object.entries preserves insertion order in modern JavaScript
      expect(result).toEqual(['z=1', 'a=2', 'm=3']);
    });
  });
});
