// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Button, Text } from '@nvidia/foundations-react-core';
import {
  parseReplacements,
  REPLACEMENT_MAP_COLUMN,
} from '@studio/components/AnonymizerRecordView/parse';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';
import {
  RESULT_PREVIEW_ROWS,
  resolveTextColumn,
} from '@studio/routes/AnonymizerJobDetailRoute/util';
import { memo, useCallback, useMemo, type ComponentProps, type FC } from 'react';

interface ResultsPreviewTableProps {
  readonly rows: readonly DataFileRow[];
  readonly textColumn: string | undefined;
  readonly onRowClick: (row: DataFileRow, indexInAllRows: number) => void;
}

const cellText = (value: unknown): string =>
  typeof value === 'object' ? JSON.stringify(value) : String(value);

const describeRow = (row: DataFileRow, textColumn: string | undefined): string => {
  const value = row[resolveTextColumn(row, textColumn)];
  return value == null ? '' : cellText(value);
};

const replacementCount = (row: DataFileRow): number =>
  parseReplacements(row[REPLACEMENT_MAP_COLUMN]).length;

export const ResultsPreviewTable: FC<ResultsPreviewTableProps> = memo(
  ({ rows, textColumn, onRowClick }) => {
    // Default columnPinning forces every column onto its literal `size`; clearing it lets the
    // unsized "Record" column flex to fill remaining space.
    const dataViewState = useStudioDataViewState({
      defaultPageSize: RESULT_PREVIEW_ROWS,
      columnPinning: {},
    });

    const { pageIndex, pageSize } = dataViewState.pagination.state;
    const pageRows = useMemo(
      () => rows.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize),
      [rows, pageIndex, pageSize]
    );

    const makeColumns = useCallback<
      ComponentProps<typeof StudioDataView<DataFileRow>>['makeColumns']
    >(
      (col) => [
        col.display({
          id: 'record',
          header: 'Record',
          cell: ({ row }) => (
            <Text kind="body/regular/sm">{describeRow(row.original, textColumn)}</Text>
          ),
        }),
        col.display({
          id: 'replacements',
          header: 'Count',
          size: 100,
          enableResizing: false,
          cell: ({ row }) => <Text kind="body/regular/sm">{replacementCount(row.original)}</Text>,
        }),
        col.display({
          id: 'details',
          header: '',
          size: 100,
          enableResizing: false,
          cell: ({ row }) => (
            <Button
              kind="tertiary"
              onClick={() => onRowClick(row.original, pageIndex * pageSize + row.index)}
            >
              Details
            </Button>
          ),
        }),
      ],
      [textColumn, onRowClick, pageIndex, pageSize]
    );

    const handleRowClick = useCallback(
      (row: DataFileRow, index: number) => onRowClick(row, pageIndex * pageSize + index),
      [onRowClick, pageIndex, pageSize]
    );

    return (
      <div className="flex flex-col min-h-[400px] max-h-[640px]">
        <StudioDataView<DataFileRow>
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          onRowClick={handleRowClick}
          attributes={{ DataViewRoot: { data: pageRows, totalCount: rows.length } }}
        />
      </div>
    );
  }
);

ResultsPreviewTable.displayName = 'ResultsPreviewTable';
