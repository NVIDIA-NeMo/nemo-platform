// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { renderHook, act } from '@testing-library/react';
import React, { ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { useQueryFromSearchParams, paginationQueryState } from './useQueryFromSearchParams';
import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  DEFAULT_PAGE_SIZE_OPTIONS,
  DEFAULT_SORT,
} from '../constants/pagination';

// Create a mock URLSearchParams that behaves like the real one
class MockURLSearchParams {
  private params: Map<string, string> = new Map();

  constructor(init?: string | URLSearchParams | Record<string, string>) {
    if (typeof init === 'string') {
      // Parse query string
      const pairs = init.replace(/^\?/, '').split('&');
      pairs.forEach((pair) => {
        const [key, value] = pair.split('=');
        if (key && value) {
          this.params.set(decodeURIComponent(key), decodeURIComponent(value));
        }
      });
    } else if (init instanceof URLSearchParams) {
      init.forEach((value, key) => this.params.set(key, value));
    } else if (init && typeof init === 'object') {
      Object.entries(init).forEach(([key, value]) => {
        this.params.set(key, value);
      });
    }
  }

  get(key: string): string | null {
    return this.params.get(key) || null;
  }

  set(key: string, value: string): void {
    this.params.set(key, value);
  }

  delete(key: string): void {
    this.params.delete(key);
  }

  has(key: string): boolean {
    return this.params.has(key);
  }

  entries(): IterableIterator<[string, string]> {
    return this.params.entries();
  }

  get size(): number {
    return this.params.size;
  }

  toString(): string {
    const pairs: string[] = [];
    this.params.forEach((value, key) => {
      pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
    });
    return pairs.join('&');
  }
}

// Mock search params that we can control
let mockSearchParamsData = new MockURLSearchParams();
const mockSetSearchParams = vi.fn();

// Mock react-router-dom
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useSearchParams: () => [mockSearchParamsData, mockSetSearchParams],
  };
});

// Mock history.replaceState
const mockReplaceState = vi.fn();
Object.defineProperty(window, 'history', {
  value: { replaceState: mockReplaceState },
  writable: true,
});

// Mock mergeURLSearchParams
vi.mock('./search', () => ({
  mergeURLSearchParams: vi.fn((base, overrides) => {
    const result = new MockURLSearchParams(base);
    Object.entries(overrides).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        result.set(key, value.toString());
      } else if (result.has(key)) {
        result.delete(key);
      }
    });
    return result.toString();
  }),
}));

const wrapper = ({ children }: { children: ReactNode }) =>
  React.createElement(BrowserRouter, null, children);

describe('useQueryFromSearchParams', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParamsData = new MockURLSearchParams();
    mockReplaceState.mockClear();
  });

  describe('initialization', () => {
    it('should initialize with default pagination query state', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.query).toEqual({
        q: undefined,
        page: DEFAULT_PAGE,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: undefined,
        order: undefined,
      });
    });

    it('should merge default custom query state with pagination state', () => {
      const defaultCustomQueryState = {
        customField: 'test',
        sort_by: 'name',
        order: 'desc' as const,
      };

      const { result } = renderHook(() => useQueryFromSearchParams({ defaultCustomQueryState }), {
        wrapper,
      });

      expect(result.current.query).toEqual({
        q: undefined,
        page: DEFAULT_PAGE,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: 'name',
        order: 'desc',
        customField: 'test',
      });
    });

    it('should parse search params when not disabled', () => {
      mockSearchParamsData = new MockURLSearchParams({
        q: 'test query',
        page: '2',
        page_size: '20',
        sort_by: 'name',
        order: 'asc',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.query).toEqual({
        q: 'test query',
        page: 2,
        page_size: 20,
        sort_by: 'name',
        order: 'asc',
      });
    });

    it('should ignore search params when disabled', () => {
      mockSearchParamsData = new MockURLSearchParams({
        q: 'test query',
        page: '2',
      });

      const { result } = renderHook(() => useQueryFromSearchParams({ disableSearchParams: true }), {
        wrapper,
      });

      expect(result.current.query).toEqual({
        q: undefined,
        page: DEFAULT_PAGE,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: undefined,
        order: undefined,
      });
    });
  });

  describe('URL search param parsing', () => {
    it('should handle invalid page numbers by using defaults', () => {
      mockSearchParamsData = new MockURLSearchParams({
        page: '0',
        page_size: '0',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.query.page).toBe(DEFAULT_PAGE);
      expect(result.current.query.page_size).toBe(DEFAULT_PAGE_SIZE);
    });

    it('should parse valid integer values for page and page_size', () => {
      mockSearchParamsData = new MockURLSearchParams({
        page: '5',
        page_size: '100',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.query.page).toBe(5);
      expect(result.current.query.page_size).toBe(100);
    });

    it('should use setInitialQuery to parse custom fields', () => {
      const setInitialQuery = vi.fn((searchParams: URLSearchParams) => ({
        customField: searchParams?.get?.('custom') || 'default',
      }));

      mockSearchParamsData = new MockURLSearchParams({
        custom: 'custom value',
      });

      const { result } = renderHook(() => useQueryFromSearchParams({ setInitialQuery }), {
        wrapper,
      });

      expect(setInitialQuery).toHaveBeenCalledWith(mockSearchParamsData);
      expect(result.current.query.customField).toBe('custom value');
    });
  });

  describe('pagination model', () => {
    it('should return correct pagination model', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.paginationModel).toEqual({
        page: DEFAULT_PAGE,
        pageSize: DEFAULT_PAGE_SIZE,
        pageSizeOptions: DEFAULT_PAGE_SIZE_OPTIONS,
      });
    });

    it('should update pagination model with custom values', () => {
      mockSearchParamsData = new MockURLSearchParams({
        page: '3',
        page_size: '25',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.paginationModel).toEqual({
        page: 3,
        pageSize: 25,
        pageSizeOptions: DEFAULT_PAGE_SIZE_OPTIONS,
      });
    });
  });

  describe('sort model', () => {
    it('should return default sort when no sort_by is set', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.sort).toBe(DEFAULT_SORT);
    });

    it('should return sort string with ascending order', () => {
      mockSearchParamsData = new MockURLSearchParams({
        sort_by: 'name',
        order: 'asc',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.sort).toBe('name');
    });

    it('should return sort string with descending order', () => {
      mockSearchParamsData = new MockURLSearchParams({
        sort_by: 'created_at',
        order: 'desc',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.sort).toBe('-created_at');
    });

    it('should handle sort with undefined order', () => {
      mockSearchParamsData = new MockURLSearchParams({
        sort_by: 'name',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.sort).toBe('name');
    });
  });

  describe('setQuery', () => {
    it('should update query state', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setQuery({ q: 'new search' });
      });

      expect(result.current.query.q).toBe('new search');
    });

    it('should merge new query with existing state', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setQuery({ q: 'search', page: 2 });
      });

      expect(result.current.query).toEqual({
        q: 'search',
        page: 2,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: undefined,
        order: undefined,
      });
    });
  });

  describe('setPaginationModel', () => {
    it('should update page', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setPaginationModel({ page: 3 });
      });

      expect(result.current.query.page).toBe(3);
    });

    it('should update page size and reset page to 1', () => {
      mockSearchParamsData = new MockURLSearchParams({
        page: '5',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setPaginationModel({ pageSize: 100 });
      });

      expect(result.current.query.page).toBe(1);
      expect(result.current.query.page_size).toBe(100);
    });

    it('should keep current page when page size matches existing page size', () => {
      mockSearchParamsData = new MockURLSearchParams({
        page: '2',
        page_size: '25',
      });

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setPaginationModel({ page: 3, pageSize: 25 });
      });

      expect(result.current.query.page).toBe(3);
      expect(result.current.query.page_size).toBe(25);
    });
  });

  describe('deleteQueryParam', () => {
    it('should delete a query parameter', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setQuery({ q: 'test', page: 2 });
      });

      act(() => {
        result.current.deleteQueryParam('q');
      });

      expect(result.current.query.q).toBeUndefined();
      expect(result.current.query.page).toBe(2);
    });
  });

  describe('updateSearchQuery', () => {
    it('should update search query with filtered values', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.updateSearchQuery({ q: 'test', page: 2 });
      });

      expect(mockReplaceState).toHaveBeenCalledWith(null, '', expect.stringContaining('?s='));
    });

    it('should handle parseQueryToParam function', () => {
      const parseQueryToParam = vi.fn((params) => ({ custom_q: params.q }));

      const { result } = renderHook(() => useQueryFromSearchParams({ parseQueryToParam }), {
        wrapper,
      });

      act(() => {
        result.current.updateSearchQuery({ q: 'test' });
      });

      expect(parseQueryToParam).toHaveBeenCalled();
    });
  });

  describe('URL synchronization', () => {
    it('should update URL when query changes', () => {
      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      act(() => {
        result.current.setQuery({ q: 'test search' });
      });

      expect(mockReplaceState).toHaveBeenCalled();
    });

    it('should not update URL automatically when search params are disabled', () => {
      mockReplaceState.mockClear();

      const { result } = renderHook(() => useQueryFromSearchParams({ disableSearchParams: true }), {
        wrapper,
      });

      mockReplaceState.mockClear();

      act(() => {
        result.current.setQuery({ q: 'test search' });
      });

      expect(mockReplaceState).not.toHaveBeenCalled();
    });

    it('should still allow manual URL updates via updateSearchQuery when disabled', () => {
      mockReplaceState.mockClear();

      const { result } = renderHook(() => useQueryFromSearchParams({ disableSearchParams: true }), {
        wrapper,
      });

      act(() => {
        result.current.updateSearchQuery({ q: 'test search' });
      });

      expect(mockReplaceState).toHaveBeenCalled();
    });
  });

  describe('constants and utilities', () => {
    it('should export correct paginationQueryState', () => {
      expect(paginationQueryState).toEqual({
        q: undefined,
        page: DEFAULT_PAGE,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: undefined,
        order: undefined,
      });
    });
  });

  describe('edge cases', () => {
    it('should handle empty search params', () => {
      mockSearchParamsData = new MockURLSearchParams();

      const { result } = renderHook(() => useQueryFromSearchParams(), { wrapper });

      expect(result.current.query).toEqual(paginationQueryState);
    });

    it('should use default values from custom query state for sort fields', () => {
      const defaultCustomQueryState = {
        sort_by: 'custom_field',
        order: 'asc' as const,
      };

      const { result } = renderHook(() => useQueryFromSearchParams({ defaultCustomQueryState }), {
        wrapper,
      });

      expect(result.current.query.sort_by).toBe('custom_field');
      expect(result.current.query.order).toBe('asc');
    });
  });
});
