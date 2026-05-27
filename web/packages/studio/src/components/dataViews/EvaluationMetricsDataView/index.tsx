// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators, type WithFilterOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import {
  getEvaluationListMetricsQueryKey,
  useEvaluationDeleteMetric,
  useEvaluationListMetrics,
} from '@nemo/sdk/generated/platform/api';
import type {
  EvaluationListMetricsParams,
  EvaluationListMetricsSort,
} from '@nemo/sdk/generated/platform/schema';
import { Badge, Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type {
  EvaluationMetricsDataViewProps,
  MetricItemWithId,
} from '@studio/components/dataViews/EvaluationMetricsDataView/types';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { EvaluationMetricBulkDeleteModal } from '@studio/components/evaluation/Metrics/EvaluationMetricBulkDeleteModal';
import {
  getEvaluationMetricDetailsRoute,
  getEvaluationMetricRunRoute,
  getNewEvaluationMetricRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { Play, Scale, X } from 'lucide-react';
import {
  type ComponentProps,
  type FC,
  type ReactNode,
  useCallback,
  useMemo,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

interface MetricTypeMeta {
  label: string;
  icon?: ReactNode;
}

const METRIC_TYPE_META: Record<string, MetricTypeMeta> = {
  'llm-judge': { label: 'LLM Judge', icon: <Scale size={10} /> },
};

const getMetricTypeMeta = (type: string): MetricTypeMeta =>
  METRIC_TYPE_META[type] ?? {
    label: type
      .split('-')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' '),
  };

export const EvaluationMetricsDataView: FC<EvaluationMetricsDataViewProps> = ({
  workspace,
  onRowClick,
}) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [metricToDelete, setMetricToDelete] = useState<MetricItemWithId | null>(null);
  const { mutateAsync: deleteMetric } = useEvaluationDeleteMetric();
  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  // Build filter object from the dataview filter state
  const metricsFilter = useMemo(() => {
    type MetricsFilter = NonNullable<EvaluationListMetricsParams['filter']>;
    const filterObj: WithFilterOperators<MetricsFilter> = {};

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
      filterObj.created_at = createdAtFilter as MetricsFilter['created_at'];
    }

    if (Object.keys(filterObj).length === 0) return undefined;
    return withOperators<MetricsFilter>(filterObj);
  }, [dataViewState.apiFilter]);

  const {
    data: evaluationsData,
    isLoading,
    refetch,
    error,
  } = useEvaluationListMetrics(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParam(dataViewState.sorting.state) as EvaluationListMetricsSort,
      filter: metricsFilter,
    },
    {
      query: {
        refetchOnMount: 'always',
        placeholderData: keepPreviousData,
      },
    }
  );

  const evaluationMetrics = useMemo<MetricItemWithId[]>(
    () =>
      (evaluationsData?.data || []).map((metric) => ({
        ...metric,
        id: metric.id ?? metric.name ?? '',
      })),
    [evaluationsData?.data]
  );

  const invalidateMetrics = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: getEvaluationListMetricsQueryKey(workspace),
    });
  }, [queryClient, workspace]);

  const hasActiveFilters = !!(
    dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0
  );

  const makeColumns: ComponentProps<typeof StudioDataView<MetricItemWithId>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowSelectionColumn, rowActionsColumn }) => [
        rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
        accessor('name', {
          header: 'Name',
          enableSorting: false,
          cell: ({ row }) => row.original.name ?? '-',
        }),
        accessor((row) => ('description' in row ? (row.description ?? '') : ''), {
          id: 'description',
          header: 'Description',
          enableSorting: false,
          cell: ({ row }) => {
            const description =
              'description' in row.original ? row.original.description : undefined;
            return description ? <>{description}</> : <>-</>;
          },
        }),
        accessor((row) => ('type' in row ? (row.type ?? '') : ''), {
          id: 'type',
          header: 'Type',
          enableSorting: false,
          size: 160,
          cell: ({ row }) => {
            const type = 'type' in row.original ? (row.original.type ?? null) : null;
            if (!type) return <>-</>;
            const meta = getMetricTypeMeta(type);
            return (
              <Badge kind="solid" color="gray">
                {meta.icon}
                {meta.label}
              </Badge>
            );
          },
        }),
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
            return createdAt ? <RelativeTime datetime={createdAt} /> : <Text>-</Text>;
          },
        }),
        accessor(() => '', {
          id: 'run',
          header: '',
          size: 152,
          enableSorting: false,
          cell: ({ row }) => (
            <Flex>
              <Button
                kind="tertiary"
                onClick={(e) => {
                  e.stopPropagation();
                  if (row.original.name) {
                    navigate(getEvaluationMetricRunRoute(workspace, row.original.name));
                  }
                }}
              >
                <Play size={12} />
                Run Evaluation
              </Button>
            </Flex>
          ),
        }),
        rowActionsColumn({
          size: ROW_ACTIONS_COLUMN_SIZE,
          cellProps: {
            attributes: {
              DropdownContent: { className: 'min-w-[140px]' },
            },
          },
          rowActions: (metric) => [
            {
              children: 'View',
              onSelect: () => {
                if (metric.name) navigate(getEvaluationMetricDetailsRoute(workspace, metric.name));
              },
            },
            {
              children: 'Delete',
              danger: true,
              onSelect: () => setMetricToDelete(metric),
            },
          ],
        }),
      ],
      [navigate, workspace]
    );

  const handleDeleteConfirm = async () => {
    if (!metricToDelete?.name) return false;
    try {
      await deleteMetric({ workspace, name: metricToDelete.name });
      invalidateMetrics();
      return true;
    } catch {
      return false;
    }
  };

  return (
    <Stack className="flex-1 min-h-0" gap="density-2xl">
      <StudioDataView<MetricItemWithId>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={onRowClick}
        renderBulkActions={({ selectedRows }) => (
          <EvaluationMetricBulkDeleteModal
            selectedMetrics={selectedRows}
            onConfirmSuccess={() => {
              invalidateMetrics();
              dataViewState.rowSelection.set({});
            }}
          />
        )}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search Metric Name',
          },
          DataViewRoot: {
            data: evaluationMetrics,
            totalCount: evaluationsData?.pagination?.total_results,
            requestStatus: error ? 'error' : isLoading ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No metrics match your search criteria"
                  actions={
                    <Button kind="tertiary" onClick={() => dataViewState.resetFilters()}>
                      <X /> Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="No Metrics"
                  emptyMessage="Create a metric to start evaluating model outputs."
                  actions={
                    <Button
                      color="brand"
                      onClick={() => navigate(getNewEvaluationMetricRoute(workspace))}
                    >
                      New Metric
                    </Button>
                  }
                />
              ),
            renderErrorState: () => (
              <ErrorMessage
                message="Failed to fetch metrics"
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
      <DeleteConfirmationModal
        open={metricToDelete !== null}
        onClose={() => setMetricToDelete(null)}
        onDelete={handleDeleteConfirm}
        title="Delete Metric"
        description={`Are you sure you want to delete "${metricToDelete?.name}"? This action cannot be undone.`}
        simpleConfirm
        successText="Successfully deleted evaluation metric"
        errorText="Failed to delete evaluation metric. Please try again."
      />
    </Stack>
  );
};
