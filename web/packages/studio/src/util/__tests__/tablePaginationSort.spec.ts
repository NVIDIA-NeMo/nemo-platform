// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { tablePaginationSort } from '@nemo/common/src/utils/tablePaginationSort';

describe('tablePaginationSort', () => {
  it('should return default values when no filter state is provided', () => {
    const result = tablePaginationSort({});

    expect(result).toEqual({
      page: 1,
      page_size: 50,
      sort: '-created_at',
    });
  });

  it('should use provided values when all properties are specified', () => {
    const filterState = {
      page: 3,
      page_size: 25,
      order: 'asc',
      sort_by: 'name',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 3,
      page_size: 25,
      sort: 'name',
    });
  });

  it('should handle desc order correctly', () => {
    const filterState = {
      page: 2,
      page_size: 10,
      order: 'desc',
      sort_by: 'updated_at',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 2,
      page_size: 10,
      sort: '-updated_at',
    });
  });

  it('should use default page when page is 0', () => {
    const filterState = {
      page: 0,
      page_size: 20,
      order: 'asc',
      sort_by: 'title',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 1,
      page_size: 20,
      sort: 'title',
    });
  });

  it('should use default page_size when page_size is 0', () => {
    const filterState = {
      page: 2,
      page_size: 0,
      order: 'desc',
      sort_by: 'status',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 2,
      page_size: 50,
      sort: '-status',
    });
  });

  it('should handle partial filter state with mixed defaults', () => {
    const filterState = {
      page: 5,
      sort_by: 'priority',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 5,
      page_size: 50,
      sort: '-priority',
    });
  });

  it('should handle undefined values correctly', () => {
    const filterState = {
      page: undefined,
      page_size: undefined,
      order: undefined,
      sort_by: undefined,
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 1,
      page_size: 50,
      sort: '-created_at',
    });
  });

  it('should handle empty string order as default desc', () => {
    const filterState = {
      page: 1,
      page_size: 30,
      order: '',
      sort_by: 'category',
    };

    const result = tablePaginationSort(filterState);

    expect(result).toEqual({
      page: 1,
      page_size: 30,
      sort: '-category',
    });
  });

  it('should preserve generic type parameter', () => {
    const filterState = {
      page: 1,
      page_size: 20,
      order: 'asc',
      sort_by: 'test_field',
    };

    const result = tablePaginationSort<string>(filterState);

    // The sort field should be typed as string
    expect(typeof result.sort).toBe('string');
    expect(result.sort).toBe('test_field');
  });
});
