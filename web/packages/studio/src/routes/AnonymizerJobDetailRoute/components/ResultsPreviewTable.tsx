// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import {
  TableExpandableCell,
  type TableExpandableCellState,
} from '@nemo/common/src/components/DataView/TableExpandableCell';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Text } from '@nvidia/foundations-react-core';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';
import { RESULT_PREVIEW_ROWS } from '@studio/routes/AnonymizerJobDetailRoute/util';
import { memo, useCallback, useMemo, type ComponentProps, type FC } from 'react';

interface ResultsPreviewTableProps {
  readonly rows: readonly DataFileRow[];
  readonly columns: readonly string[];
  readonly onExpand: (cell: TableExpandableCellState) => void;
}

const cellText = (value: unknown): string =>
  typeof value === 'object' ? JSON.stringify(value) : String(value);

/** Memoized so opening the expanded-cell modal does not re-render every cell. */
export const ResultsPreviewTable: FC<ResultsPreviewTableProps> = memo(
  ({ rows, columns, onExpand }) => {
    const dataViewState = useStudioDataViewState({ defaultPageSize: RESULT_PREVIEW_ROWS });

    const { pageIndex, pageSize } = dataViewState.pagination.state;
    const pageRows = useMemo(
      () => rows.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize),
      [rows, pageIndex, pageSize]
    );

    const makeColumns = useCallback<
      ComponentProps<typeof StudioDataView<DataFileRow>>['makeColumns']
    >(
      (col) =>
        columns.map((column) =>
          col.display({
            id: column,
            header: column,
            cell: ({ row }) => {
              const value = row.original[column];
              return value == null ? (
                <Text kind="body/regular/sm" color="secondary">
                  —
                </Text>
              ) : (
                <TableExpandableCell content={cellText(value)} title={column} onExpand={onExpand} />
              );
            },
          })
        ),
      [columns, onExpand]
    );

    return (
      <div className="flex flex-col min-h-[400px] max-h-[640px]">
        <StudioDataView<DataFileRow>
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          maxTwoLines={false}
          attributes={{ DataViewRoot: { data: pageRows, totalCount: rows.length } }}
        />
      </div>
    );
  }
);

ResultsPreviewTable.displayName = 'ResultsPreviewTable';
