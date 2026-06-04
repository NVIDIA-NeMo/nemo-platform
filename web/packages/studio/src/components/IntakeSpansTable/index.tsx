// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import { useListSpans } from '@nemo/sdk/generated/platform/api';
import {
  SpanKind,
  type ListSpansMode,
  type SpanFilter,
  type SpanSortField,
} from '@nemo/sdk/generated/platform/schema';
import { Anchor, Button, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeTelemetryDataView } from '@studio/components/IntakeTelemetryDataView';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { getIntakeSpanRoute, getIntakeTraceRoute } from '@studio/routes/utils';
import {
  formatCost,
  formatDurationMs,
  formatInteger,
  buildSpanHierarchyRows,
  getSpanDisplayName,
  getSpanDurationMs,
  getSpanSubject,
  type SpanTableRow,
} from '@studio/util/intakeTelemetry';
import { keepPreviousData } from '@tanstack/react-query';
import { type ComponentProps, type FC, type ReactNode, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const SPAN_STATUS_FILTER_OPTIONS = [
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'unknown', label: 'Unknown' },
];

const SPAN_KIND_FILTER_OPTIONS = Object.values(SpanKind).map((value) => ({
  value,
  label: value,
}));

type SpanRow = DataView.TanstackTable.Row<SpanTableRow>;

const HIERARCHY_SPACER_LIMIT = 12;

interface SpanNameCellProps {
  span: SpanTableRow;
  depth: number;
  workspace: string;
  showHierarchy: boolean;
}

const SpanNameCell: FC<SpanNameCellProps> = ({ span, depth, workspace, showHierarchy }) => {
  const label = getSpanDisplayName(span);
  const hierarchyLabel =
    span.hierarchyStatus === 'parent_outside_page'
      ? 'Parent outside page'
      : span.hierarchyStatus === 'cycle_or_unreachable'
        ? 'Unresolved hierarchy'
        : undefined;

  return (
    <div className="flex min-w-0 items-center gap-density-sm">
      {showHierarchy &&
        Array.from({ length: Math.min(depth, HIERARCHY_SPACER_LIMIT) }).map((_, index) => (
          <span
            key={`${span.span_id}-hierarchy-spacer-${index}`}
            aria-hidden
            className="w-[18px] shrink-0"
          />
        ))}
      {showHierarchy && (
        <span aria-hidden className={depth > 0 ? 'relative h-5 w-5 shrink-0' : 'w-4 shrink-0'}>
          {depth > 0 && (
            <>
              <span className="absolute left-0 top-1/2 w-full border-t border-base" />
              <span className="absolute left-0 top-0 h-1/2 border-l border-base" />
            </>
          )}
        </span>
      )}
      <Anchor asChild>
        <Link to={getIntakeSpanRoute(workspace, span.span_id)} className="truncate" title={label}>
          {label}
        </Link>
      </Anchor>
      {hierarchyLabel && (
        <Text kind="body/regular/xs" className="shrink-0 text-secondary">
          {hierarchyLabel}
        </Text>
      )}
    </div>
  );
};

export interface IntakeSpansTableProps {
  workspace?: string;
  filterTogglePortalTargetId?: string;
  fixedFilter?: SpanFilter;
  mode?: ListSpansMode;
  defaultSort?: { id: string; desc: boolean };
  defaultPageSize?: number;
  showTraceColumn?: boolean;
  showHierarchy?: boolean;
  emptyHeader?: string;
  emptyMessage?: string;
  emptyStateActions?: ReactNode;
  noResultsActions?: ReactNode;
}

export const IntakeSpansTable: FC<IntakeSpansTableProps> = ({
  workspace: workspaceProp,
  filterTogglePortalTargetId,
  fixedFilter,
  mode = 'summary',
  defaultSort = { id: 'started_at', desc: true },
  defaultPageSize,
  showTraceColumn = true,
  showHierarchy = false,
  emptyHeader = 'No Spans',
  emptyMessage = 'Spans will appear here after trace data is ingested.',
  emptyStateActions,
  noResultsActions,
}) => {
  const navigate = useNavigate();
  const routeWorkspace = useWorkspaceFromPathIfExists();
  const workspace = workspaceProp ?? routeWorkspace;
  const hasWorkspace = Boolean(workspace);
  const requestWorkspace = workspace ?? '';

  const dataViewState = useStudioDataViewState({
    defaultSort,
    defaultPageSize,
  });

  const hasActiveFilters = dataViewState.debouncedColumnFilters.length > 0;

  const {
    data: spansResponse,
    isFetching,
    error,
  } = useListSpans(
    requestWorkspace,
    {
      filter: {
        ...((dataViewState.apiFilter.filter ?? {}) as SpanFilter),
        ...(fixedFilter ?? {}),
      },
      mode,
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: showHierarchy
        ? 'started_at'
        : (getSortParamWithWhitelist(
            dataViewState.sorting.state,
            ['started_at'],
            '-started_at'
          ) as SpanSortField),
    },
    {
      query: {
        enabled: hasWorkspace,
        placeholderData: keepPreviousData,
      },
    }
  );

  const tableData = useMemo(() => {
    const spans = spansResponse?.data ?? [];
    return showHierarchy
      ? buildSpanHierarchyRows(spans)
      : spans.map((span) => ({ ...span, hierarchyDepth: 0 }));
  }, [showHierarchy, spansResponse?.data]);

  const makeColumns: ComponentProps<
    typeof IntakeTelemetryDataView<SpanTableRow>
  >['makeColumns'] = ({ accessor }) =>
    [
      accessor('status', {
        id: 'status',
        header: 'Status',
        size: 130,
        meta: {
          filter: {
            type: 'single-select' as const,
            label: 'Status',
            options: SPAN_STATUS_FILTER_OPTIONS,
          },
        },
        cell: ({ row }: { row: SpanRow }) => (
          <IntakeTelemetryStatusBadge status={row.original.status} />
        ),
      }),
      accessor('kind', {
        id: 'kind',
        header: 'Kind',
        size: 120,
        meta: {
          filter: {
            type: 'single-select' as const,
            label: 'Kind',
            options: SPAN_KIND_FILTER_OPTIONS,
          },
        },
        cell: ({ row }: { row: SpanRow }) => row.original.kind,
      }),
      accessor('span_id', {
        id: 'span_id',
        header: 'Span',
        size: 280,
        enableSorting: false,
        cell: ({ row }: { row: SpanRow }) => {
          const span = row.original;
          const depth = showHierarchy ? span.hierarchyDepth : 0;
          return (
            <SpanNameCell
              span={span}
              depth={depth}
              workspace={requestWorkspace}
              showHierarchy={showHierarchy}
            />
          );
        },
      }),
      {
        id: 'subject',
        header: 'Subject',
        enableSorting: false,
        cell: ({ row }: { row: SpanRow }) => {
          const subject = getSpanSubject(row.original);
          return (
            <Text className="truncate" title={subject}>
              {subject}
            </Text>
          );
        },
      },
      showTraceColumn &&
        accessor('trace_id', {
          id: 'trace_id',
          header: 'Trace',
          enableSorting: false,
          meta: {
            filter: {
              type: 'text' as const,
              label: 'Trace ID',
              placeholder: 'Filter by trace ID',
            },
          },
          cell: ({ row }: { row: SpanRow }) =>
            row.original.trace_id ? (
              <Anchor asChild>
                <Link
                  to={getIntakeTraceRoute(requestWorkspace, row.original.trace_id)}
                  className="truncate"
                  title={row.original.trace_id}
                >
                  {row.original.trace_id}
                </Link>
              </Anchor>
            ) : (
              '—'
            ),
        }),
      {
        id: 'duration',
        header: 'Duration',
        size: 120,
        enableSorting: false,
        cell: ({ row }: { row: SpanRow }) => formatDurationMs(getSpanDurationMs(row.original)),
      },
      {
        id: 'total_tokens',
        header: 'Tokens',
        size: 120,
        enableSorting: false,
        cell: ({ row }: { row: SpanRow }) => formatInteger(row.original.total_tokens),
      },
      {
        id: 'cost_total_usd',
        header: 'Cost',
        size: 110,
        enableSorting: false,
        cell: ({ row }: { row: SpanRow }) => formatCost(row.original.cost_total_usd),
      },
      accessor('started_at', {
        id: 'started_at',
        header: 'Started',
        size: 150,
        enableSorting: true,
        meta: {
          filter: dateTimeFilter('Started At'),
        },
        cell: ({ row }: { row: SpanRow }) => <RelativeTime datetime={row.original.started_at} />,
      }),
    ].filter(Boolean) as DataView.TanstackTable.ColumnDef<SpanTableRow>[];

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  if (!workspace) {
    return <ErrorMessage message="Workspace is required to load spans." />;
  }

  return (
    <IntakeTelemetryDataView<SpanTableRow>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      filterTogglePortalTargetId={filterTogglePortalTargetId}
      onRowClick={(span) => navigate(getIntakeSpanRoute(requestWorkspace, span.span_id))}
      attributes={{
        DataViewRoot: {
          data: tableData,
          totalCount: spansResponse?.pagination?.total_results,
          requestStatus: isFetching ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () =>
            hasActiveFilters ? (
              <TableEmptyState
                header="No Results Found"
                emptyMessage="No spans match your filters."
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
                header={emptyHeader}
                emptyMessage={emptyMessage}
                actions={emptyStateActions}
              />
            ),
        },
      }}
    />
  );
};
