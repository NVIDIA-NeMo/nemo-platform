// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationTemplateDataset } from '@studio/constants/customizationTemplates';

const HF_DATASETS_API = 'https://datasets-server.huggingface.co/rows';
const HF_MAX_ROWS_PER_REQUEST = 100;

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
      const r = await fetch(url.toString());
      if (!r.ok) throw new Error(`Failed to fetch dataset from Hugging Face: ${r.statusText}`);
      const page = (await r.json()) as { rows: Array<{ row: Record<string, unknown> }> };
      fetched += page.rows.length;
      onProgress(Math.min(fetched, total), total);
      return page;
    })
  );

  const rows = pages
    .flatMap((p) => p.rows)
    .map((r) => dataset.convertRow(r.row))
    .filter((row): row is Record<string, unknown> => row !== null);

  const trainingRows = rows.slice(0, dataset.trainingRowCount);
  const validationRows = rows.slice(
    dataset.trainingRowCount,
    dataset.trainingRowCount + dataset.validationRowCount
  );

  if (trainingRows.length === 0) throw new Error('No valid training rows were found.');
  if (dataset.validationRowCount > 0 && validationRows.length === 0) {
    throw new Error('No valid validation rows were found.');
  }

  return { training: toJsonlBlob(trainingRows), validation: toJsonlBlob(validationRows) };
};
