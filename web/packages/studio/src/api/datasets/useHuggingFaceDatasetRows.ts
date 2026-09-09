// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getRowsPageRanges,
  type HfRowsPage,
  type HuggingFaceRowsSource,
  rowsPageQueryOptions,
} from '@studio/api/datasets/huggingFaceRows';
import { useQueries, type UseQueryResult } from '@tanstack/react-query';

export interface UseHuggingFaceDatasetRowsParams {
  source: HuggingFaceRowsSource;
  /** How many rows to read from the top of the split. Paginated automatically. */
  rowCount: number;
  /** Defaults to true. Set false to hold the download until the caller is ready. */
  enabled?: boolean;
}

export interface UseHuggingFaceDatasetRowsResult {
  /** Raw rows, in split order. Undefined until every page has loaded. */
  rows: Record<string, unknown>[] | undefined;
  /** True only while requests are in flight — false when the hook is disabled. */
  isFetching: boolean;
  isError: boolean;
  error: Error | null;
  /** Rows loaded so far, for progress reporting while pages are still in flight. */
  loadedRowCount: number;
}

// Module scope keeps this referentially stable, so React Query can skip recombining (and the
// deep-equality pass over every row) on renders where no page result changed.
const combineRowPages = (
  results: UseQueryResult<HfRowsPage, Error>[]
): UseHuggingFaceDatasetRowsResult => {
  const loaded = results.map((result) => result.data).filter((page) => page !== undefined);
  return {
    rows:
      loaded.length === results.length
        ? loaded.flatMap((page) => page.rows.map((entry) => entry.row))
        : undefined,
    isFetching: results.some((result) => result.isFetching),
    isError: results.some((result) => result.isError),
    error: results.find((result) => result.error)?.error ?? null,
    loadedRowCount: loaded.reduce((sum, page) => sum + page.rows.length, 0),
  };
};

export const useHuggingFaceDatasetRows = ({
  source,
  rowCount,
  enabled = true,
}: UseHuggingFaceDatasetRowsParams): UseHuggingFaceDatasetRowsResult =>
  useQueries({
    queries: getRowsPageRanges(rowCount).map(({ offset, length }) => ({
      ...rowsPageQueryOptions(source, offset, length),
      enabled,
    })),
    combine: combineRowPages,
  });
