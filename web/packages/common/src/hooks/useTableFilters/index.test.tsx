// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { suppressConsoleError } from '@nemo/testing/utils/suppress-console';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { useTableFilters, createDefaultFilterState, BaseFilterState } from './index';

const DEFAULT_PAGE_SIZE = 50;

// Mock the useQueryFromSearchParams hook
vi.mock('@nemo/common/src/utils/useQueryFromSearchParams', () => ({
  useQueryFromSearchParams: () => ({
    updateSearchQuery: vi.fn(),
  }),
}));

// Mock use-debounce
vi.mock('use-debounce', () => ({
  useDebounce: (value: unknown) => [value], // Return the value immediately without debouncing
}));

interface TestFilterState extends BaseFilterState {
  search?: {
    name?: string;
    custom_fields?: {
      display_name?: string;
    };
  };
}

const defaultTestState: TestFilterState = {
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  sort_by: 'created_at',
  order: 'desc',
};

// Wrapper component for testing with router
const createWrapper = (initialEntries: string[] = ['/']) => {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
  );
};

describe('useTableFilters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Initialization', () => {
    it('should initialize with default state when no search params are present', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      expect(result.current.filterState).toEqual(defaultTestState);
      expect(result.current.textSearch).toBe('');
      expect(result.current.hasSearchParams).toBe(false);
    });

    it('should initialize with state from URL search params', () => {
      const searchParams = encodeURIComponent(
        JSON.stringify({
          page: 1,
          page_size: 25,
          search: { name: 'test-search' },
        })
      );

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper([`/test?s=${searchParams}`]),
        }
      );

      expect(result.current.filterState).toEqual({
        ...defaultTestState,
        page: 1,
        page_size: 25,
        search: { name: 'test-search' },
      });
      expect(result.current.hasSearchParams).toBe(true);
    });

    it('should handle malformed URL search params gracefully', () => {
      suppressConsoleError('Failed to parse filter state from URL:');
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test?s=invalid-json']),
        }
      );

      expect(result.current.filterState).toEqual(defaultTestState);
      expect(result.current.hasSearchParams).toBe(true);
    });
  });

  describe('Text Search with Custom Functions', () => {
    const extractTextSearch = (filterState: TestFilterState): string => {
      return filterState.search?.name || '';
    };

    const updateTextSearch = (
      filterState: TestFilterState,
      textSearch: string
    ): TestFilterState => {
      const newState = { ...filterState };
      if (textSearch) {
        newState.search = { ...newState.search, name: textSearch };
      } else {
        if (newState.search) {
          const searchCopy = { ...newState.search };
          delete searchCopy.name;
          if (Object.keys(searchCopy).length === 0) {
            delete newState.search;
          } else {
            newState.search = searchCopy;
          }
        }
      }
      return newState;
    };

    it('should initialize text search from filter state using custom extract function', () => {
      const initialState = {
        ...defaultTestState,
        search: { name: 'initial-search' },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            extractTextSearch,
            updateTextSearch,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      expect(result.current.textSearch).toBe('initial-search');
    });

    it('should update filter state when text search changes', async () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
            extractTextSearch,
            updateTextSearch,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.setTextSearch('new-search');
      });

      await waitFor(() => {
        expect(result.current.filterState.search?.name).toBe('new-search');
      });
    });

    it('should remove search property when text search is cleared', async () => {
      const initialState = {
        ...defaultTestState,
        search: { name: 'existing-search' },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            extractTextSearch,
            updateTextSearch,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.setTextSearch('');
      });

      await waitFor(() => {
        expect(result.current.filterState.search).toBeUndefined();
      });
    });
  });

  describe('Text Search with Built-in Field Handling', () => {
    it('should handle simple field path for text search', async () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
            textSearchField: 'name',
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.setTextSearch('test-name');
      });

      await waitFor(() => {
        expect(result.current.filterState.search?.name).toBe('test-name');
      });
    });

    it('should handle nested field path for text search', async () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
            textSearchField: ['custom_fields', 'display_name'],
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.setTextSearch('nested-search');
      });

      await waitFor(() => {
        expect(result.current.filterState.search?.custom_fields?.display_name).toBe(
          'nested-search'
        );
      });
    });

    it('should clean up empty nested objects when clearing nested text search', async () => {
      const initialState = {
        ...defaultTestState,
        search: {
          custom_fields: {
            display_name: 'existing-search',
          },
        },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            textSearchField: ['custom_fields', 'display_name'],
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.setTextSearch('');
      });

      await waitFor(() => {
        expect(result.current.filterState.search).toBeUndefined();
      });
    });

    it('should extract text search from nested field', () => {
      const initialState = {
        ...defaultTestState,
        search: {
          custom_fields: {
            display_name: 'nested-value',
          },
        },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            textSearchField: ['custom_fields', 'display_name'],
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      expect(result.current.textSearch).toBe('nested-value');
    });
  });

  describe('Sorting', () => {
    it('should update sort field and set order to desc for new sort field', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.handleSort('name');
      });

      expect(result.current.filterState.sort_by).toBe('name');
      expect(result.current.filterState.order).toBe('desc');
    });

    it('should toggle order when sorting by the same field', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      // First sort by created_at (same as default)
      act(() => {
        result.current.handleSort('created_at');
      });

      expect(result.current.filterState.order).toBe('asc'); // Should toggle from desc to asc

      // Sort by created_at again
      act(() => {
        result.current.handleSort('created_at');
      });

      expect(result.current.filterState.order).toBe('desc'); // Should toggle back to desc
    });
  });

  describe('Pagination', () => {
    it('should update page number', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.handlePaginationChange({ page: 5 });
      });

      expect(result.current.filterState.page).toBe(5);
    });

    it('should update page size', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.handlePaginationChange({ pageSize: 50 });
      });

      expect(result.current.filterState.page_size).toBe(50);
    });

    it('should update both page and page size', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.handlePaginationChange({ page: 3, pageSize: 25 });
      });

      expect(result.current.filterState.page).toBe(3);
      expect(result.current.filterState.page_size).toBe(25);
    });
  });

  describe('Reset Filters', () => {
    it('should reset text search and remove search property from filter state', () => {
      const initialState = {
        ...defaultTestState,
        search: { name: 'existing-search' },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            textSearchField: 'name',
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.resetFilters();
      });

      expect(result.current.textSearch).toBe('');
      expect(result.current.filterState.search).toBeUndefined();
    });

    it('should preserve other filter properties when resetting', () => {
      const initialState = {
        ...defaultTestState,
        page: 5,
        page_size: 25,
        search: { name: 'existing-search' },
      };

      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: initialState,
            textSearchField: 'name',
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      act(() => {
        result.current.resetFilters();
      });

      expect(result.current.filterState).toEqual({
        ...initialState,
        search: undefined,
      });
    });
  });

  describe('Debounced State', () => {
    it('should return debounced filter state', () => {
      const { result } = renderHook(
        () =>
          useTableFilters({
            defaultState: defaultTestState,
          }),
        {
          wrapper: createWrapper(['/test']),
        }
      );

      // Since we mocked debounce to return immediately, debouncedFilterState should equal filterState
      expect(result.current.debouncedFilterState).toEqual(result.current.filterState);
    });
  });
});

describe('createDefaultFilterState', () => {
  it('should create default filter state with correct defaults', () => {
    const result = createDefaultFilterState();

    expect(result).toEqual({
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      sort_by: 'created_at',
      order: 'desc',
    });
  });

  it('should merge overrides with defaults', () => {
    const overrides = {
      page: 5,
      sort_by: 'name',
      custom_field: 'custom_value',
    };

    const result = createDefaultFilterState(overrides);

    expect(result).toEqual({
      page: 5,
      page_size: DEFAULT_PAGE_SIZE,
      sort_by: 'name',
      order: 'desc',
      custom_field: 'custom_value',
    });
  });

  it('should handle typed overrides correctly', () => {
    interface CustomFilterState extends BaseFilterState {
      search?: {
        name?: string;
      };
      customProperty?: string;
    }

    const result = createDefaultFilterState<CustomFilterState>({
      search: { name: 'test' },
      customProperty: 'value',
    });

    expect(result).toEqual({
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      sort_by: 'created_at',
      order: 'desc',
      search: { name: 'test' },
      customProperty: 'value',
    });
  });
});
