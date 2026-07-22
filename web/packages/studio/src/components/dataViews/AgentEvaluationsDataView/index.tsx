// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import {
  getEvaluatorListAgentEvaluateJobsQueryKey,
  useEvaluatorDeleteAgentEvaluateJob,
  useEvaluatorListAgentEvaluateJobs,
} from '@nemo/sdk/generated/evaluator/api';
import {
  type AgentEvaluateJob,
  type AgentEvaluateJobsListFilter,
  AgentEvaluateJobsSortField,
} from '@nemo/sdk/generated/evaluator/schema';
import { Button, Stack, Text } from '@nvidia/foundations-react-core';
import {
  aggregateScoresOf,
  agentNameForJob,
  evalConfigName,
  fetchAgentEvalResultsForJobs,
} from '@studio/api/evaluation/agent-evaluations';
import { BulkDeleteModal } from '@studio/components/BulkDeleteModal';
import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { formatScore } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { getAgentEvaluationDetailRoute, getFilesetDetailRoute } from '@studio/routes/utils';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash } from 'lucide-react';
import { ComponentProps, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

type AgentEvalJobRow = AgentEvaluateJob & { id: string };

const STATUS_OPTIONS_WITH_ALL = [{ value: '', label: 'All' }, ...STATUS_FILTER_OPTIONS];

const SORTABLE_FIELDS = Object.values(AgentEvaluateJobsSortField).filter((v) => !v.startsWith('-'));
const DEFAULT_SORT = AgentEvaluateJobsSortField['-created_at'];

export const AgentEvaluationsDataView = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [deleteJobs, setDeleteJobs] = useState<AgentEvalJobRow[]>([]);

  const dataViewState = useStudioDataViewState<AgentEvaluateJobsListFilter>({
    defaultSort: [{ id: 'created_at', desc: true }],
  });

  const deleteJobMutation = useEvaluatorDeleteAgentEvaluateJob({
    mutation: {
      onSuccess: () =>
        queryClient.resetQueries({
          queryKey: getEvaluatorListAgentEvaluateJobsQueryKey(workspace),
        }),
    },
  });

  const handleDeleteJobs = async (jobsToDelete: AgentEvalJobRow[]) => {
    await Promise.all(
      jobsToDelete.map(async (job) => {
        try {
          await deleteJobMutation.mutateAsync({ workspace, name: job.name });
        } catch (error) {
          throw new Error(
            `Failed to delete "${job.name}": ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      })
    );
  };

  const {
    data: jobsData,
    isLoading,
    error,
  } = useEvaluatorListAgentEvaluateJobs(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParamWithWhitelist(
        dataViewState.sorting.state,
        SORTABLE_FIELDS,
        DEFAULT_SORT
      ) as AgentEvaluateJobsSortField,
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.apiFilter.searchText
          ? withOperators<AgentEvaluateJobsListFilter>({
              name: { $like: dataViewState.apiFilter.searchText },
            })
          : {}),
      },
    },
    {
      query: {
        placeholderData: keepPreviousData,
        staleTime: 0,
        refetchOnWindowFocus: true,
        refetchInterval: JOB_POLLING_INTERVAL_MS,
      },
    }
  );

  const jobs = useMemo<AgentEvalJobRow[]>(
    () => (jobsData?.data ?? []).map((job) => ({ ...job, id: job.id || job.name })),
    [jobsData?.data]
  );

  const jobNames = useMemo(() => jobs.map((job) => job.name).filter(Boolean), [jobs]);

  const { data: resultsByName } = useQuery({
    queryKey: ['agent-eval-results-for-jobs', workspace, jobNames] as const,
    queryFn: ({ signal }) => fetchAgentEvalResultsForJobs(workspace, jobNames, signal),
    enabled: jobNames.length > 0,
    placeholderData: keepPreviousData,
    refetchInterval: JOB_POLLING_INTERVAL_MS,
  });

  const makeColumns: ComponentProps<typeof StudioDataView<AgentEvalJobRow>>['makeColumns'] = (
    { accessor },
    { rowSelectionColumn, rowActionsColumn }
  ) => [
    rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
    accessor((original) => (original ? (evalConfigName(original) ?? '') : ''), {
      id: 'eval_config',
      header: 'Eval Config',
      size: 200,
      enableSorting: false,
      cell: ({ row }) => {
        const configName = evalConfigName(row.original);
        return configName ? (
          <Link
            to={getFilesetDetailRoute(workspace, configName)}
            className="text-primary underline"
            onClick={(e) => e.stopPropagation()}
          >
            {configName}
          </Link>
        ) : null;
      },
    }),
    accessor((original) => (original ? (agentNameForJob(original) ?? '') : ''), {
      id: 'agent',
      header: 'Agent',
      size: 200,
      enableSorting: false,
    }),
    accessor((original) => original?.name || '', {
      id: 'name',
      header: 'Job Name',
    }),
    accessor((original) => original?.status || '', {
      id: 'status',
      header: 'Status',
      size: 160,
      meta: {
        filter: {
          type: 'single-select' as const,
          label: 'Status',
          options: STATUS_OPTIONS_WITH_ALL,
        },
      },
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    }),
    accessor(() => '', {
      id: 'score',
      header: 'Score',
      size: 220,
      enableSorting: false,
      cell: ({ row }) => {
        const scores = aggregateScoresOf(resultsByName?.get(row.original.name) ?? null);
        if (scores.length === 0) return null;
        return (
          <Stack gap="density-xs">
            {scores.map((s) => (
              <Text key={s.name} kind="body/semibold/md" className="whitespace-nowrap">
                {s.name}: {formatScore(s.mean)}
              </Text>
            ))}
          </Stack>
        );
      },
    }),
    accessor((original) => original?.created_at || '', {
      id: 'created_at',
      header: 'Created',
      size: 200,
      enableSorting: true,
      cell: ({ row }) => <RelativeTime datetime={row.original.created_at ?? ''} />,
    }),
    rowActionsColumn({
      size: ROW_ACTIONS_COLUMN_SIZE,
      enableResizing: false,
      cell: ({ row }) => (
        <QuickActionsMenuRoot
          actions={[{ label: 'Delete', onSelect: () => setDeleteJobs([row.original]) }]}
        />
      ),
    }),
  ];

  const hasActiveFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;
  const isInitialEmpty = jobs.length === 0 && !isLoading && !error && !hasActiveFilters;

  if (error) {
    return (
      <TableEmptyState
        header="Failed to fetch evaluations"
        emptyMessage="An error occurred while loading evaluation jobs."
      />
    );
  }

  return (
    <>
      <StudioDataView<AgentEvalJobRow>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={(row) => {
          if (!row.name) return;
          navigate(getAgentEvaluationDetailRoute(workspace, row.name));
        }}
        renderBulkActions={({ selectedRows }) => (
          <Button
            kind="tertiary"
            aria-label="Delete selected jobs"
            onClick={() => setDeleteJobs(selectedRows)}
          >
            <Trash /> Delete
          </Button>
        )}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search by name',
          },
          DataViewRoot: {
            data: jobs,
            totalCount: jobsData?.pagination?.total_results ?? 0,
            requestStatus: isLoading && !jobsData ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              isInitialEmpty ? (
                <TableEmptyState
                  header="No evaluation jobs yet"
                  emptyMessage="Apply a model_optimization suggestion or submit an evaluate-agent job to see results here."
                />
              ) : (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No evaluation jobs match your search or filters."
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Filters
                    </Button>
                  }
                />
              ),
          },
        }}
      />

      <BulkDeleteModal
        items={deleteJobs}
        open={deleteJobs.length > 0}
        onDelete={handleDeleteJobs}
        title={(count) => `Delete ${count} Evaluation${count !== 1 ? 's' : ''}`}
        onClose={() => {
          setDeleteJobs([]);
          dataViewState.rowSelection.set({});
        }}
      />
    </>
  );
};
