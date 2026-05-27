// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators, type WithFilterOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useEvaluationListBenchmarks } from '@nemo/sdk/generated/platform/api';
import type {
  EvaluationListBenchmarksParams,
  EvaluationListBenchmarksSort,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Stack, Text } from '@nvidia/foundations-react-core';
import type {
  BenchmarkItemWithId,
  EvaluationBenchmarksDataViewProps,
} from '@studio/components/dataViews/EvaluationBenchmarksDataView/types';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { EMPTY_FIELD_EMDASH_VALUE } from '@studio/constants/constants';
import { LINK_EVAL_DOCS_BENCHMARKS } from '@studio/constants/links';
import { keepPreviousData } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo } from 'react';

export const EvaluationBenchmarksDataView: FC<EvaluationBenchmarksDataViewProps> = ({
  workspace,
  onRowClick,
}) => {
  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const benchmarksFilter = useMemo(() => {
    type BenchmarksFilter = NonNullable<EvaluationListBenchmarksParams['filter']>;
    const filterObj: WithFilterOperators<BenchmarksFilter> = {};

    const nameFilter = dataViewState.apiFilter.searchText;
    if (nameFilter) {
      filterObj.name = { $like: nameFilter };
    }

    const createdAtFilter = dataViewState.apiFilter.filter?.created_at;
    if (
      createdAtFilter &&
      typeof createdAtFilter === 'object' &&
      Object.keys(createdAtFilter).length > 0
    ) {
      filterObj.created_at = createdAtFilter as BenchmarksFilter['created_at'];
    }

    if (Object.keys(filterObj).length === 0) return undefined;
    return withOperators<BenchmarksFilter>(filterObj);
  }, [dataViewState.apiFilter]);

  const {
    data: benchmarksResponse,
    isFetching,
    refetch,
    error,
  } = useEvaluationListBenchmarks(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParam(dataViewState.sorting.state) as EvaluationListBenchmarksSort,
      filter: benchmarksFilter,
    },
    {
      query: {
        placeholderData: keepPreviousData,
      },
    }
  );

  const benchmarks = useMemo<BenchmarkItemWithId[]>(
    () =>
      (benchmarksResponse?.data || []).map((b) => ({
        ...b,
        id: b.id ?? b.name ?? '',
      })),
    [benchmarksResponse?.data]
  );

  const hasActiveFilters = !!(
    dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0
  );

  const makeColumns: ComponentProps<typeof StudioDataView<BenchmarkItemWithId>>['makeColumns'] =
    useCallback(
      ({ accessor }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: true,
          cell: ({ row }) => row.original.name ?? EMPTY_FIELD_EMDASH_VALUE,
        }),
        accessor(
          (row) =>
            'description' in row
              ? (row.description ?? EMPTY_FIELD_EMDASH_VALUE)
              : EMPTY_FIELD_EMDASH_VALUE,
          {
            id: 'description',
            header: 'Description',
            enableSorting: false,
            size: 280,
          }
        ),
        accessor(
          (row) => ('metrics' in row && Array.isArray(row.metrics) ? row.metrics.length : null),
          {
            id: 'metrics_count',
            header: 'Metrics',
            enableSorting: false,
            size: 100,
            cell: ({ getValue }) => {
              const count = getValue();
              return <Text>{count !== null ? count : EMPTY_FIELD_EMDASH_VALUE}</Text>;
            },
          }
        ),
        accessor(
          (row) => {
            if (!('dataset' in row)) return '—';
            const { dataset } = row;
            if (typeof dataset === 'string') return dataset;
            if (dataset !== null && typeof dataset === 'object' && 'name' in dataset) {
              return String((dataset as { name: string }).name);
            }
            return EMPTY_FIELD_EMDASH_VALUE;
          },
          {
            id: 'dataset',
            header: 'Dataset',
            enableSorting: false,
          }
        ),
        accessor('created_at', {
          id: 'created_at',
          header: 'Created',
          enableSorting: true,
          size: 150,
          meta: {
            filter: dateTimeFilter('Created At'),
          },
          cell: ({ row }) => {
            const createdAt = 'created_at' in row.original ? row.original.created_at : undefined;
            return createdAt ? <RelativeTime datetime={createdAt} /> : EMPTY_FIELD_EMDASH_VALUE;
          },
        }),
      ],
      []
    );

  return (
    <Stack className="flex-1 min-h-0" gap="density-2xl">
      <StudioDataView<BenchmarkItemWithId>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={onRowClick}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search benchmark name',
          },
          DataViewRoot: {
            data: benchmarks,
            totalCount: benchmarksResponse?.pagination?.total_results,
            requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No benchmarks match your search criteria"
                  actions={
                    <Button kind="tertiary" onClick={() => dataViewState.resetFilters()}>
                      <X /> Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="No Benchmarks"
                  emptyMessage="No benchmarks are defined for this workspace yet."
                  actions={<DocumentationButton href={LINK_EVAL_DOCS_BENCHMARKS} />}
                />
              ),
            renderErrorState: () => (
              <ErrorMessage
                message="Failed to fetch benchmarks"
                slotFooter={
                  <Button type="button" kind="tertiary" onClick={() => refetch()}>
                    Retry
                  </Button>
                }
              />
            ),
          },
        }}
      />
    </Stack>
  );
};
