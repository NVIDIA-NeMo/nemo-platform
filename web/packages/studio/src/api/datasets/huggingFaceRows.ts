// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { queryOptions } from '@tanstack/react-query';

export const HF_DATASETS_API = 'https://datasets-server.huggingface.co/rows';
const HF_MAX_ROWS_PER_REQUEST = 100;
const HF_REQUEST_TIMEOUT_MS = 15_000;
const HF_MAX_RETRIES = 2;
const HF_RETRY_BASE_DELAY_MS = 300;

export interface HfRowsPage {
  rows: Array<{ row: Record<string, unknown> }>;
}

const isRowRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isHfRowsPage = (value: unknown): value is HfRowsPage =>
  typeof value === 'object' &&
  value !== null &&
  Array.isArray((value as { rows?: unknown }).rows) &&
  (value as { rows: unknown[] }).rows.every(
    (entry) =>
      typeof entry === 'object' && entry !== null && isRowRecord((entry as { row?: unknown }).row)
  );

export interface HuggingFaceRowsSource {
  hfDataset: string;
  hfConfig: string;
  hfSplit: string;
}

/** A page fetch that failed in a way worth retrying: network blip, timeout, rate limit, or 5xx. */
class TransientRowsPageError extends Error {}

const isTransientStatus = (status: number): boolean => status === 429 || status >= 500;

/** Splits a row count into the offset/length pages the datasets server accepts. */
export const getRowsPageRanges = (totalRows: number): Array<{ offset: number; length: number }> =>
  Array.from({ length: Math.ceil(totalRows / HF_MAX_ROWS_PER_REQUEST) }, (_, i) => {
    const offset = i * HF_MAX_ROWS_PER_REQUEST;
    return { offset, length: Math.min(HF_MAX_ROWS_PER_REQUEST, totalRows - offset) };
  });

const buildRowsPageUrl = (
  source: HuggingFaceRowsSource,
  offset: number,
  length: number
): string => {
  const url = new URL(HF_DATASETS_API);
  url.searchParams.set('dataset', source.hfDataset);
  url.searchParams.set('config', source.hfConfig);
  url.searchParams.set('split', source.hfSplit);
  url.searchParams.set('offset', String(offset));
  url.searchParams.set('length', String(length));
  return url.toString();
};

const fetchRowsPage = async (url: string, querySignal: AbortSignal): Promise<HfRowsPage> => {
  const controller = new AbortController();
  const abortFromQuery = () => controller.abort();
  if (querySignal.aborted) controller.abort();
  else querySignal.addEventListener('abort', abortFromQuery);

  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, HF_REQUEST_TIMEOUT_MS);

  try {
    let response: Response;
    try {
      response = await fetch(url, { signal: controller.signal });
    } catch (e) {
      // A cancelled query (unmount, cancelQueries) must not be retried; a timeout still should.
      if (querySignal.aborted && !timedOut) throw e;
      const reason = timedOut
        ? `timed out after ${HF_REQUEST_TIMEOUT_MS}ms`
        : e instanceof Error
          ? e.message
          : 'request failed';
      throw new TransientRowsPageError(`Failed to fetch dataset from Hugging Face: ${reason}`);
    }

    if (response.ok) {
      const payload: unknown = await response.json();
      if (!isHfRowsPage(payload)) {
        throw new Error('Failed to fetch dataset from Hugging Face: unexpected response shape');
      }
      return payload;
    }

    const message = `Failed to fetch dataset from Hugging Face: ${response.statusText || 'request failed'}`;
    throw isTransientStatus(response.status)
      ? new TransientRowsPageError(message)
      : new Error(message);
  } finally {
    clearTimeout(timeoutId);
    querySignal.removeEventListener('abort', abortFromQuery);
  }
};

export const rowsPageQueryOptions = (
  source: HuggingFaceRowsSource,
  offset: number,
  length: number
) =>
  queryOptions({
    queryKey: [
      'huggingface-rows-page',
      source.hfDataset,
      source.hfConfig,
      source.hfSplit,
      offset,
      length,
    ],
    queryFn: ({ signal }) => fetchRowsPage(buildRowsPageUrl(source, offset, length), signal),
    staleTime: Infinity,
    retry: (failureCount: number, error: Error) =>
      failureCount < HF_MAX_RETRIES && error instanceof TransientRowsPageError,
    retryDelay: (attemptIndex: number) => HF_RETRY_BASE_DELAY_MS * 2 ** attemptIndex,
  });
