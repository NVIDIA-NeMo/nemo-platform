// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { parseDataFile } from '@studio/components/FileRowEditor/parse';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';
import {
  metadataTextColumn,
  orderResultColumns,
  parseArtifactUrl,
  RESULT_PREVIEW_ROWS,
} from '@studio/routes/AnonymizerJobDetailRoute/util';
import { useMemo } from 'react';

export interface ResultPreview {
  readonly rows: DataFileRow[];
  readonly columns: string[];
  readonly isLoading: boolean;
  readonly error: Error | null;
}

/** Reads the first {@link RESULT_PREVIEW_ROWS} rows of a finished job's result fileset. */
export const useResultPreview = (
  workspace: string,
  artifactUrl: string | undefined
): ResultPreview => {
  const location = parseArtifactUrl(artifactUrl);
  const enabled = !!location;

  const { data: metadata } = useDatasetFileContent({
    workspace,
    name: location?.fileset ?? '',
    path: `${location?.basePath}/metadata.json`,
    enabled,
  });

  const {
    data: dataset,
    isLoading,
    error,
  } = useDatasetFileContent({
    workspace,
    name: location?.fileset ?? '',
    path: `${location?.basePath}/dataset.parquet`,
    range: [0, RESULT_PREVIEW_ROWS],
    enabled,
  });

  const rows = useMemo<DataFileRow[]>(() => {
    if (!dataset) return [];
    // parseDataFile throws on a malformed line; no route error boundary is wired.
    try {
      return parseDataFile(dataset, 'jsonl');
    } catch {
      return [];
    }
  }, [dataset]);

  const columns = useMemo(
    () =>
      rows.length ? orderResultColumns(Object.keys(rows[0]), metadataTextColumn(metadata)) : [],
    [rows, metadata]
  );

  return { rows, columns, isLoading, error };
};
