// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useInnerDataViewContext } from '@nemo/common/src/components/DataView/internal/context';
import {
  getCellStyle,
  getColumnWidths,
} from '@nemo/common/src/components/DataView/internal/hooks/useResizableColumns';
import {
  StatusResult,
  type StatusResultProps,
} from '@nemo/common/src/components/DataView/internal/StatusResult';
import { TableColumnHeader } from '@nemo/common/src/components/DataView/internal/TableColumnHeader';
import type { IntentionalAny } from '@nemo/common/src/components/DataView/internal/types';
import { getCellTitle } from '@nemo/common/src/components/DataView/internal/utils/cell-utils';
import { getHeaderId } from '@nemo/common/src/components/DataView/internal/utils/header-utils';
import {
  TableBody as KuiTableBody,
  TableDataCell,
  TableHead,
  TableRoot,
  type TableRootProps,
  TableRow,
} from '@nvidia/foundations-react-core';
import { flexRender, type Row, type Table as ReactTableType } from '@tanstack/react-table';
import type { Virtualizer } from '@tanstack/react-virtual';
import classnames from 'classnames';
import {
  Fragment,
  forwardRef,
  memo,
  useCallback,
  useMemo,
  type CSSProperties,
  type JSX,
  type ReactNode,
} from 'react';

export interface TableContentProps
  extends TableRootProps, Pick<StatusResultProps, 'renderEmptyState' | 'renderErrorState'> {
  /** If provided, limits rendering to the number of rows passed. */
  rowLimit?: number;
  /** Slot for the status result component (empty/error states). */
  slotStatusResult?: ReactNode;
  /** If true, the table header will be sticky. @defaultValue false */
  stickyTableHeader?: boolean;
  virtualizer?: Virtualizer<HTMLTableElement, HTMLElement>;
}

const TABLE_VARIABLES = {
  '--subrow-indent': 'var(--spacing-density-3xl)',
} as CSSProperties;

/**
 * The DataView Table content component. For virtualized tables, use `VirtualizedTableContent`.
 */
export const TableContent = forwardRef<HTMLTableElement, TableContentProps>(
  (
    {
      className,
      rowLimit,
      renderEmptyState,
      renderErrorState,
      slotStatusResult,
      style,
      stickyTableHeader = false,
      virtualizer,
      ...props
    },
    ref
  ) => {
    const { autoCellTooltips, isDataViewEmptyState, isDataViewErrorState, state, table } =
      useInnerDataViewContext();
    const hasPinnedColumns = Object.keys(state.columnPinning.state).length > 0;
    const columnSizing = table.getState().columnSizing;
    const tableColumns = table.getAllColumns();
    const columnWidths = useMemo(
      () =>
        getColumnWidths({
          columnSizing,
          columns: tableColumns,
          disableAutoSizing: hasPinnedColumns,
        }),
      // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-compute when column count changes, not on every column reference
      [hasPinnedColumns, columnSizing, tableColumns.length]
    );
    if (state.displayMode.state !== 'table') {
      return null;
    }
    return (
      <div className="min-h-fit w-full overflow-auto">
        <TableRoot
          className={classnames(
            className,
            'w-full overflow-auto',
            '[&_thead,&_thead_th,td]:bg-surface-base [&_tbody_tr]:data-[is-subrow]:bg-surface-raised [&_tbody_tr]:data-[is-subrow]:[&_td]:bg-surface-raised',
            '[&_tbody_tr]:hover:[&,&>td]:bg-gray-025 dark:[&_tbody_tr]:hover:[&,&>td]:bg-gray-900',
            '[&_tbody_tr]:data-[highlight]:[&,&>td]:bg-gray-050 dark:[&_tbody_tr]:data-[highlight]:[&,&>td]:bg-gray-800'
          )}
          ref={ref}
          // eslint-disable-next-line no-restricted-syntax -- column widths are dynamic via CSS variables
          style={{ ...TABLE_VARIABLES, ...columnWidths, ...style }}
          {...props}
        >
          <TableHead className={classnames(stickyTableHeader && 'sticky top-0 z-10')}>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableColumnHeader
                    key={header.id}
                    automaticTitles={autoCellTooltips}
                    className={classnames(
                      'relative',
                      header.column.getIsLastColumn('left') &&
                        'shadow-[inset_-4px_0_4px_-4px_var(--color-gray-400)]',
                      header.column.getIsFirstColumn('right') &&
                        'shadow-[inset_4px_0_4px_-4px_var(--color-gray-400)]'
                    )}
                    header={header}
                    // eslint-disable-next-line no-restricted-syntax -- pinned column offsets are dynamic
                    style={getCellStyle({
                      column: header.column,
                      disableAutoSizing: !!virtualizer,
                    })}
                  />
                ))}
              </TableRow>
            ))}
          </TableHead>
          {!isDataViewEmptyState && !isDataViewErrorState && (
            <TableBody table={table} virtualizer={virtualizer} rowLimit={rowLimit} />
          )}
        </TableRoot>
        {slotStatusResult ?? (
          <StatusResult renderEmptyState={renderEmptyState} renderErrorState={renderErrorState} />
        )}
      </div>
    );
  }
);
TableContent.displayName = 'TableContent';

/** @deprecated Use `TableContent` instead. */
export const Table = TableContent;

interface TableBodyProps {
  table: ReactTableType<IntentionalAny>;
  virtualizer?: Virtualizer<HTMLTableElement, HTMLElement>;
  rowLimit?: number;
}

function TableBody(props: TableBodyProps): JSX.Element {
  const { autoCellTooltips, renderCustomRowExpansion, table, state } = useInnerDataViewContext();
  const showMemoizedBody = table.getState().columnSizingInfo.isResizingColumn && !props.virtualizer;
  const highlightedRowId = state.rowHighlight.state;
  const BodyComponent = useMemo(
    () => (showMemoizedBody ? MemoizedBody : InnerTableBody),
    [showMemoizedBody]
  );
  return (
    <BodyComponent
      autoCellTooltips={autoCellTooltips}
      highlightedRowId={highlightedRowId}
      renderCustomRowExpansion={renderCustomRowExpansion}
      {...props}
    />
  );
}

interface InnerTableBodyProps extends TableBodyProps {
  autoCellTooltips: boolean;
  highlightedRowId: string | number | undefined;
  renderCustomRowExpansion?: (data: { row: Row<IntentionalAny> }) => JSX.Element;
}

function InnerTableBody({
  autoCellTooltips,
  highlightedRowId,
  renderCustomRowExpansion,
  rowLimit,
  table,
  virtualizer,
}: InnerTableBodyProps): JSX.Element {
  const { rows } = table.getRowModel();
  const measureElementRef = useCallback(
    (node: HTMLTableRowElement | null) => {
      if (node && virtualizer) {
        virtualizer.measureElement(node);
      }
    },
    [virtualizer]
  );
  const rowsToRender = virtualizer
    ? virtualizer.getVirtualItems()
    : rowLimit
      ? rows.slice(0, rowLimit)
      : rows;
  return (
    <KuiTableBody
      // eslint-disable-next-line no-restricted-syntax -- virtualized total height is dynamic
      style={virtualizer ? { height: `${virtualizer.getTotalSize()}px` } : undefined}
    >
      {rowsToRender.map((item) => {
        const row = (virtualizer ? rows[(item as { index: number }).index] : item) as
          | Row<IntentionalAny>
          | undefined;
        const isSelected = !!highlightedRowId && row?.id === highlightedRowId;
        let foundFirstNonPrebuiltColumn = false;
        return (
          <Fragment key={row?.id ?? (item as { index: number }).index}>
            <TableRow
              data-index={(item as { index?: number }).index}
              data-row-id={row?.id}
              data-is-subrow={(row?.depth && row.depth > 0) || undefined}
              data-has-subrow={(row?.subRows.length && row.subRows.length > 0) || undefined}
              data-highlight={isSelected || undefined}
              ref={measureElementRef}
              // eslint-disable-next-line no-restricted-syntax -- virtualized translate is dynamic
              style={
                virtualizer
                  ? { transform: `translateY(${(item as { start: number }).start}px)` }
                  : undefined
              }
            >
              {row?.getVisibleCells().map((cell) => {
                let isFirstNonPrebuiltColumn = false;
                if (
                  !foundFirstNonPrebuiltColumn &&
                  !cell.column.columnDef.meta?._isPrebuiltColumn
                ) {
                  foundFirstNonPrebuiltColumn = true;
                  isFirstNonPrebuiltColumn = true;
                }
                return (
                  <TableDataCell
                    key={cell.id}
                    align={cell.column.columnDef.meta?.alignment}
                    className={classnames(
                      'data-[pinned]:sticky data-[pinned]:z-10',
                      'data-[within-subrow]:data-[first-non-prebuilt-column]:!pl-[var(--subrow-indent,var(--table-cell-inline-padding))]',
                      cell.column.getIsLastColumn('left') &&
                        'shadow-[inset_-4px_0_4px_-4px_var(--color-gray-400)]',
                      cell.column.getIsFirstColumn('right') &&
                        'shadow-[inset_4px_0_4px_-4px_var(--color-gray-400)]'
                    )}
                    data-first-non-prebuilt-column={isFirstNonPrebuiltColumn || undefined}
                    data-pinned={cell.column.getIsPinned() || undefined}
                    data-within-subrow={(row?.depth && row.depth > 0) || undefined}
                    headers={getHeaderId(cell.column.id)}
                    title={autoCellTooltips ? getCellTitle(cell) || undefined : undefined}
                    // eslint-disable-next-line no-restricted-syntax -- pinned column offsets are dynamic
                    style={getCellStyle({
                      column: cell.column,
                      disableAutoSizing: !!virtualizer,
                    })}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableDataCell>
                );
              })}
            </TableRow>
            {row?.getIsExpanded() && renderCustomRowExpansion && (
              <TableRow>
                <TableDataCell colSpan={row.getVisibleCells().length}>
                  {renderCustomRowExpansion({ row })}
                </TableDataCell>
              </TableRow>
            )}
          </Fragment>
        );
      })}
    </KuiTableBody>
  );
}

const MemoizedBody = memo(
  InnerTableBody,
  (prev, next) => prev.table.options.data === next.table.options.data
);
