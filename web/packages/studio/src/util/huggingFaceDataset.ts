// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationTemplateDataset } from '@studio/constants/customizationTemplates';

const HF_DATASETS_API = 'https://datasets-server.huggingface.co/rows';
const HF_MAX_ROWS_PER_REQUEST = 100;
/** Abort a single page request if the server never responds. */
const HF_REQUEST_TIMEOUT_MS = 15_000;
/** Retries per page after the first attempt (so up to HF_MAX_RETRIES + 1 attempts). */
const HF_MAX_RETRIES = 2;
const HF_RETRY_BASE_DELAY_MS = 300;

interface HfRowsPage {
  rows: Array<{ row: Record<string, unknown> }>;
}

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** 429 and 5xx are worth retrying; 4xx (bad dataset/config) are not. */
const isTransientStatus = (status: number): boolean => status === 429 || status >= 500;

/**
 * Fetches one page of rows with a request timeout and bounded exponential backoff.
 * Retries transient failures (network errors, timeouts, 429/5xx) and throws a
 * clear error once retries are exhausted, so a page never hangs indefinitely.
 */
const fetchRowsPage = async (url: string): Promise<HfRowsPage> => {
  for (let attempt = 0; ; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), HF_REQUEST_TIMEOUT_MS);
    let response: Response | undefined;
    let networkError: unknown;
    try {
      response = await fetch(url, { signal: controller.signal });
    } catch (e) {
      networkError = e;
    } finally {
      clearTimeout(timeoutId);
    }

    if (response?.ok) return (await response.json()) as HfRowsPage;

    const canRetry =
      attempt < HF_MAX_RETRIES &&
      (networkError !== undefined ||
        (response !== undefined && isTransientStatus(response.status)));
    if (!canRetry) {
      const reason =
        networkError instanceof Error
          ? networkError.message
          : response?.statusText || 'request failed';
      throw new Error(`Failed to fetch dataset from Hugging Face: ${reason}`);
    }

    await delay(HF_RETRY_BASE_DELAY_MS * 2 ** attempt);
  }
};

const toJsonlBlob = (rows: Record<string, unknown>[]): Blob =>
  new Blob([rows.map((row) => JSON.stringify(row)).join('\n')], {
    type: 'application/x-ndjson',
  });

/**
 * Fetches a public Hugging Face dataset (via the datasets-server rows API),
 * converts each row with the template's `convertRow`, and splits the result into
 * training and validation JSONL blobs ready to upload as a fileset.
 *
 * Pages are fetched in parallel; `onProgress` reports rows fetched vs. the total
 * requested. Throws if the dataset can't be fetched or yields too few valid rows.
 */
export const fetchAndConvertDataset = async (
  dataset: CustomizationTemplateDataset,
  onProgress: (fetched: number, total: number) => void
): Promise<{ training: Blob; validation: Blob }> => {
  const total = dataset.trainingRowCount + dataset.validationRowCount;
  const pageCount = Math.ceil(total / HF_MAX_ROWS_PER_REQUEST);
  let fetched = 0;

  const pages = await Promise.all(
    Array.from({ length: pageCount }, async (_, i) => {
      const offset = i * HF_MAX_ROWS_PER_REQUEST;
      const length = Math.min(HF_MAX_ROWS_PER_REQUEST, total - offset);
      const url = new URL(HF_DATASETS_API);
      url.searchParams.set('dataset', dataset.hfDataset);
      url.searchParams.set('config', dataset.hfConfig);
      url.searchParams.set('split', dataset.hfSplit);
      url.searchParams.set('offset', String(offset));
      url.searchParams.set('length', String(length));
      const page = await fetchRowsPage(url.toString());
      fetched += page.rows.length;
      onProgress(Math.min(fetched, total), total);
      return page;
    })
  );

  const rows = pages
    .flatMap((p) => p.rows)
    .map((r) => dataset.convertRow(r.row))
    .filter((row): row is Record<string, unknown> => row !== null);

  // Partition the *valid* rows by the configured counts. Dropped (invalid) rows
  // shrink the pool, so guard against either set coming up short rather than only
  // catching a fully-empty one.
  const trainingRows = rows.slice(0, dataset.trainingRowCount);
  const validationRows = rows.slice(
    dataset.trainingRowCount,
    dataset.trainingRowCount + dataset.validationRowCount
  );

  if (trainingRows.length < dataset.trainingRowCount) {
    throw new Error(
      `Not enough valid training rows: needed ${dataset.trainingRowCount}, found ${trainingRows.length}.`
    );
  }
  if (dataset.validationRowCount > 0 && validationRows.length < dataset.validationRowCount) {
    throw new Error(
      `Not enough valid validation rows: needed ${dataset.validationRowCount}, found ${validationRows.length}.`
    );
  }

  return { training: toJsonlBlob(trainingRows), validation: toJsonlBlob(validationRows) };
};
