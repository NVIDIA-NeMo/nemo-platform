// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Banner,
  Panel,
  Spinner,
  Stack,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
  Text,
} from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import {
  orderResultColumns,
  parseArtifactUrl,
  parseJsonLines,
  RESULT_PREVIEW_ROWS,
} from '@studio/routes/AnonymizerJobDetailRoute/util';
import { useMemo, type FC } from 'react';

interface ResultsPreviewPanelProps {
  readonly workspace: string;
  readonly artifactUrl: string | undefined;
}

type ResultRow = Record<string, unknown>;

const renderCell = (value: unknown): string => {
  if (value == null) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

export const ResultsPreviewPanel: FC<ResultsPreviewPanelProps> = ({ workspace, artifactUrl }) => {
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

  const rows = useMemo(() => parseJsonLines<ResultRow>(dataset), [dataset]);

  const columns = useMemo(() => {
    if (!rows.length) return [];
    let textColumn: string | undefined;
    try {
      textColumn = (JSON.parse(metadata ?? '{}') as { original_text_column?: string })
        .original_text_column;
    } catch {
      textColumn = undefined;
    }
    return orderResultColumns(Object.keys(rows[0]), textColumn);
  }, [rows, metadata]);

  return (
    <Panel slotHeading="Preview" elevation="high" density="compact">
      {error ? (
        <Banner kind="inline" status="error">
          Could not load the result preview.
        </Banner>
      ) : isLoading ? (
        <Spinner aria-label="Loading preview" />
      ) : rows.length ? (
        <Stack gap="density-md">
          <div className="overflow-auto max-h-[28rem]">
            <TableRoot className="bg-transparent w-full" align="left">
              <TableHead>
                <TableRow>
                  {columns.map((column) => (
                    <TableHeaderCell key={column}>{column}</TableHeaderCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow key={index}>
                    {columns.map((column) => (
                      <TableDataCell key={column} className="align-top max-w-md">
                        <span className="line-clamp-6 whitespace-pre-wrap">
                          {renderCell(row[column])}
                        </span>
                      </TableDataCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </TableRoot>
          </div>
          <Text kind="body/regular/sm">
            Showing the first {rows.length} records. Download the result for the full dataset.
          </Text>
        </Stack>
      ) : (
        <Text kind="body/regular/md">No preview available for this job.</Text>
      )}
    </Panel>
  );
};
