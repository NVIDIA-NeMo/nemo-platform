// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { logger } from '@nemo/common/src/utils/logger';

export const DEFAULT_FETCH_ALL_PAGE_SIZE = 100;
export const DEFAULT_FETCH_ALL_MAX_PAGES = 1000;

export interface PaginatedResponse<T> {
  data?: T[];
  pagination?: { total_pages?: number };
}

export interface FetchAllPagesOptions {
  pageSize?: number;
  maxPages?: number;
}

/**
 * Drains a page-numbered list endpoint. Takes the fetcher rather than the SDK
 * function so it stays free of `@nemo/sdk` and can ship in the plugin surface.
 */
export const fetchAllPages = async <T>(
  fetchPage: (page: number, pageSize: number) => Promise<PaginatedResponse<T>>,
  {
    pageSize = DEFAULT_FETCH_ALL_PAGE_SIZE,
    maxPages = DEFAULT_FETCH_ALL_MAX_PAGES,
  }: FetchAllPagesOptions = {}
): Promise<T[]> => {
  const all: T[] = [];

  for (let page = 1; page <= maxPages; page += 1) {
    const response = await fetchPage(page, pageSize);
    const batch = response.data ?? [];
    all.push(...batch);

    const totalPages = response.pagination?.total_pages;
    if (totalPages ? page >= totalPages : batch.length < pageSize) return all;

    if (page === maxPages) {
      logger.warn(`[fetchAllPages] stopped at the ${maxPages}-page cap; results are truncated`);
    }
  }

  return all;
};
