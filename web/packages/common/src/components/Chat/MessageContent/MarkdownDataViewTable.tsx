// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getMarkdownTableOptions,
  parseMarkdownTable,
} from '@nemo/common/src/components/Chat/MessageContent/helpers';
import { MarkdownTableCell } from '@nemo/common/src/components/Chat/MessageContent/MarkdownTableCell';
import type {
  MarkdownDataViewTableProps,
  MarkdownTableRow,
} from '@nemo/common/src/components/Chat/MessageContent/types';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { type FC, type MouseEvent, useCallback, useMemo, useState } from 'react';

export const MarkdownDataViewTable: FC<MarkdownDataViewTableProps> = ({ children, options }) => {
  const tableOptions = useMemo(() => getMarkdownTableOptions(options), [options]);
  const { columns, rows } = useMemo(() => parseMarkdownTable(children), [children]);
  const dataViewState = DataView.useDataViewState();
  const [expandedRowIds, setExpandedRowIds] = useState<ReadonlySet<string>>(() => new Set());
  const data = useMemo(
    () => rows.map((row) => ({ ...row, expandedRowIds })),
    [expandedRowIds, rows]
  );
  const toggleExpandedRow = useCallback((rowId: string) => {
    setExpandedRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  }, []);
  const handleTableClick = useCallback(
    (event: MouseEvent<HTMLTableElement>) => {
      if (!tableOptions.expandableCells || !(event.target instanceof Element)) return;

      const rowElement = event.target.closest('tbody tr[data-row-id]');
      const rowId = rowElement?.getAttribute('data-row-id');
      if (!rowId) return;

      toggleExpandedRow(rowId);
    },
    [tableOptions.expandableCells, toggleExpandedRow]
  );
  const makeColumns = useMemo<DataView.MakeColumns<MarkdownTableRow>>(
    () => (columnHelper) =>
      columns.map((column, columnIndex) =>
        columnHelper.accessor((row) => row.cellValues[columnIndex] ?? '', {
          id: column.id,
          header: () => column.header,
          cell: ({ row }) => {
            return (
              <MarkdownTableCell
                expanded={row.original.expandedRowIds?.has(row.original.id) ?? false}
                expandable={tableOptions.expandableCells}
                onToggle={() => toggleExpandedRow(row.original.id)}
              >
                {row.original.cells[columnIndex] ?? ''}
              </MarkdownTableCell>
            );
          },
          enableResizing: false,
          enableSorting: true,
        })
      ),
    [columns, tableOptions, toggleExpandedRow]
  );

  if (!columns.length) return null;

  return (
    <DataView.Root
      autoCellTooltips={false}
      className="my-density-md min-w-0 max-w-full overflow-hidden [&>div]:min-h-0"
      data={data}
      dataMode="sort-filter-only"
      makeColumns={makeColumns}
      state={dataViewState}
      totalCount={rows.length}
    >
      <DataView.Toolbar>
        <DataView.SearchBar debounce={0} placeholder="Search table" />
      </DataView.Toolbar>
      <DataView.TableContent
        className={`min-h-0 border-0 [&_.nv-table-head]:border-b-0 [&_.nv-table-row]:border-b-0 [&_thead_th>.data-view-header-control]:!max-w-none [&_.data-view-header-control>span]:!overflow-visible [&_.data-view-header-control>span]:!text-clip ${tableOptions.expandableCells ? '[&_tbody_tr]:cursor-pointer' : ''}`}
        density="compact"
        layout="auto"
        onClick={handleTableClick}
        stickyTableHeader={false}
      />
    </DataView.Root>
  );
};
