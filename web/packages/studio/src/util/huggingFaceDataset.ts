// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getRowsPageRanges, rowsPageQueryOptions } from '@studio/api/datasets/huggingFaceRows';
import type { CustomizationTemplateDataset } from '@studio/constants/customizationTemplates';
import type { QueryClient } from '@tanstack/react-query';

const toJsonlBlob = (rows: Record<string, unknown>[]): Blob =>
  new Blob([rows.map((row) => JSON.stringify(row)).join('\n')], {
    type: 'application/x-ndjson',
  });

export const fetchAndConvertDataset = async (
  queryClient: QueryClient,
  dataset: CustomizationTemplateDataset,
  onProgress: (fetched: number, total: number) => void
): Promise<{ training: Blob; validation: Blob }> => {
  const total = dataset.trainingRowCount + dataset.validationRowCount;
  let fetched = 0;

  const pages = await Promise.all(
    getRowsPageRanges(total).map(async ({ offset, length }) => {
      const page = await queryClient.ensureQueryData(rowsPageQueryOptions(dataset, offset, length));
      fetched += page.rows.length;
      onProgress(Math.min(fetched, total), total);
      return page;
    })
  );

  const rawRows = pages.flatMap((p) => p.rows).map((entry) => entry.row);

  const convert = (raw: Record<string, unknown>[]): Record<string, unknown>[] =>
    raw
      .map((row) => dataset.convertRow(row))
      .filter((row): row is Record<string, unknown> => row !== null);

  const trainingRows = convert(rawRows.slice(0, dataset.trainingRowCount));
  const validationRows = convert(
    rawRows.slice(dataset.trainingRowCount, dataset.trainingRowCount + dataset.validationRowCount)
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
