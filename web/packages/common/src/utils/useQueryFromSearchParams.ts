// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';

import { removeEmptyValues } from './removeEmptyValues';
import { mergeURLSearchParams } from './search';
import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  DEFAULT_PAGE_SIZE_OPTIONS,
  DEFAULT_SORT,
} from '../constants/pagination';

export type PaginationQueryState = {
  q?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  order?: 'asc' | 'desc';
};

const filterAndSort = (obj: object) =>
  Object.fromEntries(
    Object.entries(obj)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, v?.toString()])
      .sort(([a], [b]) => a.localeCompare(b))
  );

const compareObjects = (a: object, b: object): boolean => {
  return JSON.stringify(filterAndSort(a)) === JSON.stringify(filterAndSort(b));
};

export const paginationQueryState: PaginationQueryState = {
  q: undefined,
  page: DEFAULT_PAGE,
  page_size: DEFAULT_PAGE_SIZE,
  sort_by: undefined,
  order: undefined,
};

export type UseQueryFromSearchParamsOptions<K> = {
  defaultCustomQueryState?: K & PaginationQueryState;
  setInitialQuery?: (searchParams: URLSearchParams) => K;
  parseQueryToParam?: (searchParams: object) => Record<string, string | undefined>;
  disableSearchParams?: boolean;
};

/**
 * Reads pagination/sort/filter state from the URL search params, using it to
 * set the user's current query.
 *
 * TODO (#474): Use Zod validation to correct malformed URLSearchParams
 */
export function useQueryFromSearchParams<K>({
  defaultCustomQueryState,
  setInitialQuery,
  parseQueryToParam,
  disableSearchParams,
}: UseQueryFromSearchParamsOptions<K> = {}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const initialQuery = {
    ...paginationQueryState,
    ...defaultCustomQueryState,
  } as K & PaginationQueryState;

  const parseParams = (searchParams?: URLSearchParams): PaginationQueryState & K => {
    const init = setInitialQuery?.(searchParams ?? ({} as URLSearchParams)) || ({} as K);

    return {
      ...initialQuery,
      q: searchParams?.get('q') || undefined,
      page:
        searchParams?.get('page') && searchParams?.get('page') !== '0'
          ? parseInt(searchParams.get('page')!)
          : DEFAULT_PAGE,
      page_size:
        searchParams?.get('page_size') && searchParams?.get('page_size') !== '0'
          ? parseInt(searchParams.get('page_size')!)
          : DEFAULT_PAGE_SIZE,
      sort_by: searchParams?.get('sort_by') || defaultCustomQueryState?.sort_by,
      order: (searchParams?.get('order') as 'asc' | 'desc') || defaultCustomQueryState?.order,
      ...init,
    };
  };

  const [query, setQuery] = useState<PaginationQueryState & K>(() =>
    !disableSearchParams ? parseParams(searchParams) : parseParams()
  );

  useEffect(() => {
    if (!disableSearchParams) {
      const currentSearchParams = Object.fromEntries(searchParams.entries());
      const hasSearchQueryState = Object.entries(currentSearchParams).some(([k]) => k in query);

      if (
        (!compareObjects(query, initialQuery) &&
          !compareObjects(query, parseParams(searchParams))) ||
        (compareObjects(query, initialQuery) && hasSearchQueryState)
      ) {
        const nonDefaultParams = Object.fromEntries(
          Object.entries(query).map(([k, v]) =>
            initialQuery?.[k as keyof PaginationQueryState | keyof K] === v
              ? [k, undefined]
              : [k, v]
          )
        );

        setSearchParams((prev) =>
          mergeURLSearchParams(prev, parseQueryToParam?.(nonDefaultParams) ?? nonDefaultParams)
        );
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    if (!disableSearchParams) {
      if (searchParams.size === 0 && !compareObjects(query, initialQuery)) {
        setQuery(() => parseParams(new URLSearchParams({})));
      } else if (!compareObjects(query, parseParams(searchParams))) {
        setQuery((prevState) => ({
          ...prevState,
          ...parseParams(searchParams),
        }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const deleteQueryParam = (name: keyof PaginationQueryState | keyof K) => {
    setQuery((prev) => {
      delete prev[name];
      return prev;
    });
  };

  /**
   * Used when managing state outside of this hook, to update the URL search params
   */
  const updateSearchQuery = (newQuery: PaginationQueryState | K) => {
    // Filter out undefined values from newQuery to preserve initialQuery fallbacks
    const filteredNewQuery = Object.fromEntries(
      Object.entries(newQuery as Record<string, unknown>).filter(([, v]) => v !== undefined)
    );

    const state = {
      ...initialQuery,
      ...filteredNewQuery,
    };

    const nonDefaultParams = Object.fromEntries(
      Object.entries(state).map(([k, v]) =>
        initialQuery?.[k as keyof PaginationQueryState | keyof K] === v ? [k, undefined] : [k, v]
      )
    );

    // Remove empty objects and values before creating the search string
    const cleanedParams = removeEmptyValues(
      parseQueryToParam?.(nonDefaultParams) ?? nonDefaultParams
    );
    const searchString = cleanedParams ? JSON.stringify(cleanedParams) : '{}';

    // Preserve existing page, page_size, and sort URL params (used by useStudioDataViewState)
    const currentParams = new URLSearchParams(window.location.search);
    const preservedParams = new URLSearchParams();

    // Keep page, page_size, and sort if they exist
    const pageParam = currentParams.get('page');
    const pageSizeParam = currentParams.get('page_size');
    const sortParam = currentParams.get('sort');
    if (pageParam) preservedParams.set('page', pageParam);
    if (pageSizeParam) preservedParams.set('page_size', pageSizeParam);
    if (sortParam) preservedParams.set('sort', sortParam);

    // Add the 's' param if there's content
    if (searchString && searchString !== '{}') {
      preservedParams.set('s', searchString);
    }

    const queryString = preservedParams.toString();

    history.replaceState(
      null,
      '',
      `${window.location.pathname}${queryString ? `?${queryString}` : ''}${window.location.hash}`
    );
  };

  const handlePaginationModelChange = ({
    page,
    pageSize,
  }: {
    page?: number;
    pageSize?: number;
  }) => {
    setQuery((prevState) => ({
      ...prevState,
      page: !pageSize || pageSize === query.page_size ? page || query.page : 1,
      ...(pageSize && { page_size: pageSize }),
    }));
  };

  const paginationModel = {
    page: query.page ?? DEFAULT_PAGE,
    pageSize: query.page_size ?? DEFAULT_PAGE_SIZE,
    pageSizeOptions: DEFAULT_PAGE_SIZE_OPTIONS,
  };

  const sortModel = query.sort_by ? [{ field: query.sort_by, sort: query.order }] : [];

  const sort = sortModel[0]
    ? `${sortModel[0].sort === 'desc' ? '-' : ''}${sortModel[0].field}`
    : DEFAULT_SORT;

  return {
    query,
    setQuery: (newQuery: PaginationQueryState | K) =>
      setQuery((prevState) => ({
        ...prevState,
        ...newQuery,
      })),
    deleteQueryParam,
    paginationModel,
    setPaginationModel: handlePaginationModelChange,
    sort,
    updateSearchQuery,
  };
}
