// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import { useListTraces } from '@nemo/sdk/generated/platform/api';
import type { Trace, TraceFilter, TraceSortField } from '@nemo/sdk/generated/platform/schema';
import { Badge, Button } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeTelemetryDataView } from '@studio/components/IntakeLists/IntakeTelemetryDataView';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { getIntakeTraceRoute } from '@studio/routes/utils';
import {
  formatCost,
  formatDurationMs,
  formatInteger,
  getTraceDisplayName,
} from '@studio/util/intakeTelemetry';
import { keepPreviousData } from '@tanstack/react-query';
import type { ComponentProps, FC, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

export interface IntakeTracesTableProps {
  workspace?: string;
  filterTogglePortalTargetId?: string;
  emptyStateActions?: ReactNode;
  noResultsActions?: ReactNode;
}

export const IntakeTracesTable: FC<IntakeTracesTableProps> = ({
  workspace: workspaceProp,
  filterTogglePortalTargetId,
  emptyStateActions,
  noResultsActions,
}) => {
  const navigate = useNavigate();
  const routeWorkspace = useWorkspaceFromPathIfExists();
  const workspace = workspaceProp ?? routeWorkspace;
  const hasWorkspace = Boolean(workspace);
  const requestWorkspace = workspace ?? '';

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'started_at', desc: true },
  });

  const hasActiveFilters = dataViewState.debouncedColumnFilters.length > 0;

  const {
    data: tracesResponse,
    isFetching,
    error,
  } = useListTraces(
    requestWorkspace,
    {
      filter: (dataViewState.apiFilter.filter ?? {}) as TraceFilter,
      mode: 'detailed',
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParamWithWhitelist(
        dataViewState.sorting.state,
        ['started_at'],
        '-started_at'
      ) as TraceSortField,
    },
    {
      query: {
        enabled: hasWorkspace,
        placeholderData: keepPreviousData,
      },
    }
  );

  const makeColumns: ComponentProps<typeof IntakeTelemetryDataView<Trace>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor('id', {
      id: 'id',
      header: 'Trace',
      size: 280,
      enableSorting: false,
      meta: {
        filter: {
          type: 'text' as const,
          label: 'Trace ID',
          placeholder: 'Filter by trace ID',
        },
      },
      cell: ({ row }) => {
        const trace = row.original;
        const label = getTraceDisplayName(trace);
        return label;
      },
    }),
    {
      id: 'duration_ms',
      header: 'Duration',
      size: 120,
      enableSorting: false,
      cell: ({ row }) => formatDurationMs(row.original.duration_ms),
    },
    {
      id: 'span_count',
      header: 'Spans',
      size: 90,
      enableSorting: false,
      cell: ({ row }) => formatInteger(row.original.span_count),
    },
    {
      id: 'error_count',
      header: 'Errors',
      size: 90,
      enableSorting: false,
      cell: ({ row }) => {
        const errorCount = row.original.error_count ?? 0;
        return errorCount > 0 ? (
          <Badge kind="solid" color="red">
            {formatInteger(errorCount)}
          </Badge>
        ) : (
          formatInteger(errorCount)
        );
      },
    },
    {
      id: 'total_tokens',
      header: 'Tokens',
      size: 120,
      enableSorting: false,
      cell: ({ row }) => formatInteger(row.original.total_tokens),
    },
    {
      id: 'cost_usd',
      header: 'Cost',
      size: 110,
      enableSorting: false,
      cell: ({ row }) => formatCost(row.original.cost_usd),
    },
    accessor('started_at', {
      id: 'started_at',
      header: 'Started',
      size: 150,
      enableSorting: true,
      meta: {
        filter: dateTimeFilter('Started At'),
      },
      cell: ({ row }) => <RelativeTime datetime={row.original.started_at} />,
    }),
  ];

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  if (!workspace) {
    return <ErrorMessage message="Workspace is required to load traces." />;
  }

  return (
    <IntakeTelemetryDataView<Trace>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      filterTogglePortalTargetId={filterTogglePortalTargetId}
      onRowClick={(trace) => navigate(getIntakeTraceRoute(requestWorkspace, trace.id))}
      attributes={{
        DataViewRoot: {
          data: tracesResponse?.data ?? [],
          totalCount: tracesResponse?.pagination?.total_results,
          requestStatus: isFetching ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () =>
            hasActiveFilters ? (
              <TableEmptyState
                header="No Results Found"
                emptyMessage="No traces match your search or filters."
                actions={
                  noResultsActions ?? (
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Filters
                    </Button>
                  )
                }
              />
            ) : (
              <TableEmptyState
                header="No Traces"
                emptyMessage="Trace summaries will appear here after spans are ingested."
                actions={emptyStateActions}
              />
            ),
        },
      }}
    />
  );
};
