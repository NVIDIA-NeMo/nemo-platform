// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { useState, useEffect, useCallback, SetStateAction, Dispatch } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useDebounce } from 'use-debounce';

import {
  PaginationQueryState,
  useQueryFromSearchParams,
} from '../../utils/useQueryFromSearchParams';

const DEFAULT_PAGE_SIZE = 50;

export interface BaseFilterState<TSearchState = unknown> extends PaginationQueryState {
  search?: TSearchState;
  filter?: object;
}

export interface UseTableFiltersOptions<TFilterState extends BaseFilterState> {
  defaultState?: TFilterState;
  extractTextSearch?: (filterState: TFilterState) => string;
  updateTextSearch?: (filterState: TFilterState, textSearch: string) => TFilterState;
  textSearchField?: string | string[]; // Path to the search field, e.g., 'name' or ['custom_fields', 'display_name']
}

export interface UseTableFiltersReturn<TFilterState extends BaseFilterState> {
  filterState: TFilterState;
  setFilterState: Dispatch<SetStateAction<TFilterState>>;
  textSearch: string;
  setTextSearch: Dispatch<SetStateAction<string>>;
  debouncedFilterState: TFilterState;
  hasSearchParams: boolean;
  resetFilters: () => void;
  handleSort: (sortBy: string) => void;
  handlePaginationChange: (pagination: { page?: number; pageSize?: number }) => void;
}

// Helper function to get nested property value
const getNestedValue = (
  obj: Record<string, unknown> | undefined,
  path: string | string[]
): string => {
  if (!obj) return '';
  if (typeof path === 'string') {
    return (obj[path] as string) || '';
  }
  return (
    (path.reduce((current, key) => {
      if (current && typeof current === 'object' && key in current) {
        return (current as Record<string, unknown>)[key];
      }
      return undefined;
    }, obj as unknown) as string) || ''
  );
};

// Helper function to set nested property value
const setNestedValue = (
  obj: Record<string, unknown> | undefined,
  path: string | string[],
  value: string
): Record<string, unknown> => {
  if (typeof path === 'string') {
    const result = { ...(obj || {}) };
    if (value !== '') {
      result[path] = value;
    } else {
      delete result[path];
    }
    return result;
  }

  // Handle nested path
  const result = { ...(obj || {}) };
  let current: Record<string, unknown> = result;

  // Navigate to the parent of the target property
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    if (!current[key]) {
      current[key] = {};
    } else {
      current[key] = { ...(current[key] as Record<string, unknown>) };
    }
    current = current[key] as Record<string, unknown>;
  }

  const lastKey = path[path.length - 1];
  if (value !== '') {
    current[lastKey] = value;
  } else {
    delete current[lastKey];

    // Clean up empty parent objects from bottom to top
    const parentObj = result;
    const pathToClean = [...path];
    pathToClean.pop(); // Remove the last key as we already handled it

    while (pathToClean.length > 0) {
      const currentPath = pathToClean.slice();
      let target: Record<string, unknown> = parentObj;

      // Navigate to the object that might be empty
      for (let i = 0; i < currentPath.length - 1; i++) {
        target = target[currentPath[i]] as Record<string, unknown>;
      }

      const keyToCheck = currentPath[currentPath.length - 1];
      const targetObj = target[keyToCheck] as Record<string, unknown> | undefined;
      if (targetObj && Object.keys(targetObj).length === 0) {
        delete target[keyToCheck];
        pathToClean.pop();
      } else {
        break;
      }
    }
  }

  return result;
};

export function useTableFilters<TFilterState extends BaseFilterState>({
  defaultState = {} as TFilterState,
  extractTextSearch,
  updateTextSearch,
  textSearchField,
}: UseTableFiltersOptions<TFilterState>): UseTableFiltersReturn<TFilterState> {
  const [searchParams] = useSearchParams();
  const { updateSearchQuery } = useQueryFromSearchParams<TFilterState>({
    defaultCustomQueryState: defaultState,
    disableSearchParams: true,
  });
  const hasSearchParams = !!searchParams.get('s');

  // Initialize filter state from URL params
  const [filterState, setFilterState] = useState<TFilterState>(() => {
    const search = searchParams.get('s');
    let query = {};
    if (search) {
      try {
        query = JSON.parse(decodeURIComponent(search));
      } catch (e) {
        console.error('Failed to parse filter state from URL:', e);
      }
    }
    return {
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      ...defaultState,
      ...query,
    };
  });

  // Built-in text search functions
  const createBuiltInExtractTextSearch =
    <TFilterState extends BaseFilterState>(textSearchField: string | string[]) =>
    (filterState: TFilterState): string => {
      return getNestedValue(
        filterState?.search as Record<string, unknown> | undefined,
        textSearchField
      );
    };

  const createBuiltInUpdateTextSearch =
    <TFilterState extends BaseFilterState>(textSearchField: string | string[]) =>
    (filterState: TFilterState, textSearch: string): TFilterState => {
      const state = { ...filterState } as TFilterState;

      if (textSearch !== '') {
        state.search = {
          ...(state.search || {}),
          ...setNestedValue(
            state.search as Record<string, unknown> | undefined,
            textSearchField,
            textSearch
          ),
        };
      } else {
        if (state.search) {
          const updatedSearch = setNestedValue(
            state.search as Record<string, unknown>,
            textSearchField,
            ''
          );
          if (Object.keys(updatedSearch).length === 0) {
            delete state.search;
          } else {
            state.search = updatedSearch;
          }
        }
      }

      return state;
    };

  // Use built-in text search if textSearchField is provided and custom functions are not
  const finalExtractTextSearch =
    extractTextSearch ||
    (textSearchField ? createBuiltInExtractTextSearch<TFilterState>(textSearchField) : undefined);
  const finalUpdateTextSearch =
    updateTextSearch ||
    (textSearchField ? createBuiltInUpdateTextSearch<TFilterState>(textSearchField) : undefined);

  // Initialize text search from filter state
  const [textSearch, setTextSearch] = useState(() => {
    if (finalExtractTextSearch) {
      return finalExtractTextSearch(filterState);
    }
    return '';
  });

  const [debouncedFilterState] = useDebounce(filterState, DEFAULT_DEBOUNCE_MS);
  const [debouncedTextSearch] = useDebounce(textSearch, DEFAULT_DEBOUNCE_MS);

  // Reset filters function
  const resetFilters = useCallback(() => {
    setTextSearch('');
    setFilterState((curr) => {
      const state = { ...curr };
      delete state.search;
      delete state.filter;
      return state;
    });
  }, []);

  // Sort handler
  const handleSort = useCallback(
    (sortBy: string) =>
      setFilterState((prev) => ({
        ...prev,
        sort_by: sortBy,
        order:
          (prev.sort_by || 'created_at') !== sortBy
            ? 'desc'
            : (prev.order || 'desc') === 'desc'
              ? 'asc'
              : 'desc',
      })),
    []
  );

  // Pagination handler
  const handlePaginationChange = useCallback((pagination: { page?: number; pageSize?: number }) => {
    const update: { page_size?: number; page?: number } = {};
    if (pagination.pageSize) {
      update.page_size = pagination.pageSize;
    }
    if (pagination.page) {
      update.page = pagination.page;
    }
    setFilterState((curr) => ({
      ...curr,
      ...update,
    }));
  }, []);

  // Update filter state when text search changes
  useEffect(() => {
    if (finalUpdateTextSearch) {
      const updatedState = finalUpdateTextSearch(filterState, debouncedTextSearch);
      const currentSearchValue = finalExtractTextSearch ? finalExtractTextSearch(filterState) : '';
      if (currentSearchValue !== debouncedTextSearch) {
        setFilterState(updatedState);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedTextSearch, finalUpdateTextSearch]);

  // Update URL params when filter state changes
  useEffect(() => {
    updateSearchQuery(debouncedFilterState);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedFilterState]);

  return {
    filterState,
    setFilterState,
    textSearch,
    setTextSearch,
    debouncedFilterState,
    hasSearchParams,
    resetFilters,
    handleSort,
    handlePaginationChange,
  };
}

// Create a default state factory
export const createDefaultFilterState = <TFilterState extends BaseFilterState>(
  overrides?: Partial<TFilterState>
): TFilterState =>
  ({
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
    sort_by: 'created_at',
    order: 'desc',
    ...overrides,
  }) as TFilterState;
