// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import {
  DETECTED_ENTITIES_COLUMN,
  FINAL_ENTITIES_COLUMN,
  REPLACEMENT_MAP_COLUMN,
} from '@studio/components/AnonymizerRecordView/parse';
import { parseDataFile } from '@studio/components/FileRowEditor/parse';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';
import {
  metadataTextColumn,
  parseArtifactUrl,
  RESULT_PREVIEW_ROWS,
} from '@studio/routes/AnonymizerJobDetailRoute/util';
import { useMemo } from 'react';

const TRACE_COLUMNS = [DETECTED_ENTITIES_COLUMN, FINAL_ENTITIES_COLUMN, REPLACEMENT_MAP_COLUMN];

/** Only the entity/replacement columns are pulled from the trace row — everything else stays from `dataset.parquet`. */
const pickTraceColumns = (row: DataFileRow | undefined): Partial<DataFileRow> => {
  if (!row) return {};
  const picked: Partial<DataFileRow> = {};
  for (const column of TRACE_COLUMNS) {
    if (column in row) picked[column] = row[column];
  }
  return picked;
};

export interface ResultPreview {
  readonly rows: DataFileRow[];
  readonly textColumn: string | undefined;
  readonly isLoading: boolean;
  readonly error: Error | null;
}

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

  /** `dataset.parquet` drops entity/replacement columns for Replace-mode jobs; only `trace.parquet` has them. */
  const { data: trace } = useDatasetFileContent({
    workspace,
    name: location?.fileset ?? '',
    path: `${location?.basePath}/trace.parquet`,
    range: [0, RESULT_PREVIEW_ROWS],
    enabled,
  });

  const traceRows = useMemo<DataFileRow[]>(() => {
    if (!trace) return [];
    try {
      return parseDataFile(trace, 'jsonl');
    } catch {
      return [];
    }
  }, [trace]);

  const datasetRows = useMemo<DataFileRow[]>(() => {
    if (!dataset) return [];
    try {
      return parseDataFile(dataset, 'jsonl');
    } catch {
      return [];
    }
  }, [dataset]);

  const rows = useMemo<DataFileRow[]>(
    () =>
      datasetRows.map((row, index) => ({
        ...row,
        ...pickTraceColumns(traceRows[index]),
      })),
    [datasetRows, traceRows]
  );

  const textColumn = useMemo(() => metadataTextColumn(metadata), [metadata]);

  return { rows, textColumn, isLoading, error };
};
