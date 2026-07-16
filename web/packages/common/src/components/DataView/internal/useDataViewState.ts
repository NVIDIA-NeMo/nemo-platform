// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  ColumnFiltersState,
  ColumnOrderState,
  ColumnPinningState,
  ExpandedState,
  PaginationState,
  RowSelectionState,
  SortingState,
} from '@tanstack/react-table';
import { useCallback, useState } from 'react';

const DEFAULT_PAGE_SIZE = 25;

interface PaginationDefaultState extends Partial<PaginationState> {
  paginationOptions?: number[];
}

function usePaginationState(defaultState: PaginationDefaultState = {}) {
  const [newPage, setNewPage] = useState<PaginationState & { paginationOptions?: number[] }>({
    pageIndex: defaultState.pageIndex ?? 0,
    pageSize: defaultState.pageSize ?? (defaultState.paginationOptions?.[0] || DEFAULT_PAGE_SIZE),
    paginationOptions: defaultState.paginationOptions,
  });
  const goToFirstPage = useCallback(() => {
    setNewPage((p) => ({ ...p, pageIndex: 0 }));
  }, [setNewPage]);
  return {
    isPageIndexDirty:
      defaultState.pageIndex !== undefined && newPage.pageIndex !== defaultState.pageIndex,
    isPageSizeDirty:
      defaultState.pageSize !== undefined && newPage.pageSize !== defaultState.pageSize,
    /** The page being currently rendered, 0 indexed. */
    state: newPage,
    /** State setter for pagination state. */
    set: setNewPage,
    /** Reset pagination to the first page. */
    goToFirstPage,
  };
}

function useSortingState(defaultState?: SortingState) {
  const [sortingState, setSorting] = useState<SortingState>(defaultState ?? []);
  return { state: sortingState, set: setSorting };
}

function useSearchBar(defaultState?: string) {
  const [searchFilter, setSearchFilter] = useState(defaultState ?? '');
  return { state: searchFilter, set: setSearchFilter };
}

function useColumnFilters(defaultState: ColumnFiltersState = []) {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>(defaultState);
  return { state: columnFilters, set: setColumnFilters };
}

function useColumnOrder(defaultState: ColumnOrderState = []) {
  const [columnOrder, setColumnOrder] = useState<ColumnOrderState>(defaultState);
  return { state: columnOrder, set: setColumnOrder };
}

function useColumnPinning(defaultState: ColumnPinningState = {}) {
  const [columnPinning, setColumnPinning] = useState<ColumnPinningState>(defaultState);
  return { state: columnPinning, set: setColumnPinning };
}

function useColumnVisibility(defaultState: Record<string, boolean> = {}) {
  const [state, setColumnVisibility] = useState<Record<string, boolean>>(defaultState);
  return { state, set: setColumnVisibility };
}

function useExpansion(defaultState?: ExpandedState) {
  const [state, set] = useState<ExpandedState>(defaultState || {});
  return { state, set };
}

function useRowHighlight(defaultState?: string | number) {
  const [state, setRowHighlight] = useState<string | number | undefined>(defaultState);
  return { state, set: setRowHighlight };
}

function useDisplayModeState(defaultState: string = 'table') {
  const [state, set] = useState<string>(defaultState);
  return { state, set };
}

function useTab(defaultState?: string) {
  const [state, set] = useState<string | undefined>(defaultState);
  return { state, set };
}

function useRowSelection() {
  const [state, set] = useState<RowSelectionState>({});
  return { state, set };
}

/**
 * A hook to be used with the DataView component to manage state and access table state.
 *
 * @example
 * ```tsx
 * const tableState = DataView.useDataViewState();
 * return <DataView.Root state={tableState} ... />;
 * ```
 */
export function useDataViewState(defaultState?: {
  columnFilters?: ColumnFiltersState;
  columnOrder?: ColumnOrderState;
  columnPinning?: ColumnPinningState;
  columnVisibility?: Record<string, boolean>;
  displayMode?: 'card' | 'table';
  pagination?: Partial<PaginationState> & { paginationOptions?: number[] };
  expansion?: ExpandedState;
  rowHighlight?: string;
  searchBar?: string;
  sorting?: SortingState;
  tab?: string;
}) {
  return {
    columnFiltering: useColumnFilters(defaultState?.columnFilters),
    columnOrder: useColumnOrder(defaultState?.columnOrder),
    columnPinning: useColumnPinning(defaultState?.columnPinning),
    columnVisibility: useColumnVisibility(defaultState?.columnVisibility),
    displayMode: useDisplayModeState(defaultState?.displayMode),
    expansion: useExpansion(defaultState?.expansion),
    pagination: usePaginationState(defaultState?.pagination),
    rowHighlight: useRowHighlight(defaultState?.rowHighlight),
    rowSelection: useRowSelection(),
    searchBar: useSearchBar(defaultState?.searchBar),
    sorting: useSortingState(defaultState?.sorting),
    tab: useTab(defaultState?.tab),
  };
}

export type DataViewState = ReturnType<typeof useDataViewState>;
