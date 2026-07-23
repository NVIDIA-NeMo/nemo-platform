// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import * as DataView from '@nemo/common/src/components/DataView/internal';
import { useRowClick } from '@nemo/common/src/components/DataView/useRowClick';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { DEFAULT_PAGE_SIZE_OPTIONS } from '@nemo/common/src/constants/pagination';
import { Button, Text } from '@nvidia/foundations-react-core';
import { type EvalAuthorRun, useOptimizerListEvalAuthorRuns } from '@studio/api/optimizer';
import { getOptimizerEvalAuthorRunRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { FileCode2 } from 'lucide-react';
import { type ComponentProps, type FC } from 'react';
import { useNavigate } from 'react-router-dom';

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);

const isEvalAuthorRun = (value: unknown): value is EvalAuthorRun => {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<EvalAuthorRun>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.status === 'string' &&
    typeof candidate.stage === 'string' &&
    !!candidate.outputs &&
    Array.isArray(candidate.outputs.metric_names)
  );
};

const duration = (run: EvalAuthorRun): string => {
  if (!run.started_at) return '—';
  const end = run.completed_at ? Date.parse(run.completed_at) : Date.now();
  const seconds = Math.max(0, Math.round((end - Date.parse(run.started_at)) / 1_000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
};

const makeColumns: ComponentProps<typeof DataView.Root<EvalAuthorRun>>['makeColumns'] = ({
  accessor,
}) => [
  accessor('name', {
    header: 'Run',
    enableSorting: false,
    size: 220,
    cell: ({ getValue }) => <Text>{getValue()}</Text>,
  }),
  accessor('status', {
    header: 'Status',
    enableSorting: false,
    size: 110,
    cell: ({ getValue }) => <StatusBadge status={getValue()} />,
  }),
  accessor('stage', {
    header: 'Stage',
    enableSorting: false,
    size: 150,
    cell: ({ getValue }) => <Text>{getValue().replaceAll('_', ' ')}</Text>,
  }),
  accessor('outputs', {
    id: 'metrics',
    header: 'Metrics',
    enableSorting: false,
    size: 220,
    cell: ({ getValue }) => <Text>{getValue()?.metric_names.join(', ') || '—'}</Text>,
  }),
  accessor('outputs', {
    id: 'train_task_count',
    header: 'Train',
    enableSorting: false,
    size: 72,
    cell: ({ getValue }) => <Text>{getValue()?.train_task_count ?? '—'}</Text>,
  }),
  accessor('outputs', {
    id: 'validation_task_count',
    header: 'Validation',
    enableSorting: false,
    size: 88,
    cell: ({ getValue }) => <Text>{getValue()?.validation_task_count ?? '—'}</Text>,
  }),
  accessor('started_at', {
    header: 'Started',
    enableSorting: false,
    size: 120,
    cell: ({ getValue }) => (getValue() ? <RelativeTime datetime={getValue()!} /> : <Text>—</Text>),
  }),
  accessor('completed_at', {
    id: 'duration',
    header: 'Duration',
    enableSorting: false,
    size: 100,
    cell: ({ row }) => <Text>{duration(row.original)}</Text>,
  }),
];

interface InsightEvalAuthorRunsProps {
  workspace: string;
  insightId: string;
}

export const InsightEvalAuthorRuns: FC<InsightEvalAuthorRunsProps> = ({ workspace, insightId }) => {
  const navigate = useNavigate();
  const dataViewState = DataView.useDataViewState({
    pagination: { paginationOptions: DEFAULT_PAGE_SIZE_OPTIONS },
  });
  const { pageIndex, pageSize } = dataViewState.pagination.state;
  const params = {
    page: pageIndex + 1,
    page_size: pageSize,
    sort: '-created_at',
    insight_id: insightId,
  };
  const {
    data: response,
    isError,
    isFetching,
    refetch,
  } = useOptimizerListEvalAuthorRuns(workspace, params, {
    query: {
      placeholderData: keepPreviousData,
      refetchInterval: (query) =>
        query.state.data?.data?.some((run) => !TERMINAL_STATUSES.has(run.status)) ? 5_000 : false,
    },
  });
  const runs = (response?.data ?? []).filter(isEvalAuthorRun);
  const { wrapColumns, onClick, className } = useRowClick(
    (run: EvalAuthorRun) => navigate(getOptimizerEvalAuthorRunRoute(workspace, insightId, run.id)),
    runs
  );

  return (
    <DataView.Root
      className="min-h-[240px]"
      dataMode="manual"
      state={dataViewState}
      data={runs}
      totalCount={response?.pagination?.total_results ?? 0}
      requestStatus={isError ? 'error' : isFetching ? 'loading' : undefined}
      loadingRows={pageSize}
      makeColumns={wrapColumns(makeColumns)}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <DataView.TableContent
          className={`min-h-0 flex-1 overflow-auto ${className}`}
          onClick={onClick}
          renderEmptyState={() => (
            <TableEmptyState
              header="No Eval Author runs"
              emptyMessage="Eval Author has not attempted to create a verifier for this insight."
              icon={<FileCode2 className="size-12" />}
            />
          )}
          renderErrorState={() => (
            <ErrorMessage
              header="Failed to load Eval Author runs"
              message="The authoring attempts for this insight could not be loaded."
              slotFooter={
                <Button type="button" kind="tertiary" onClick={() => void refetch()}>
                  Retry
                </Button>
              }
            />
          )}
        />
        <DataView.Pagination
          className="px-density-md py-density-sm"
          showItemsPerPage
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        />
      </div>
    </DataView.Root>
  );
};
