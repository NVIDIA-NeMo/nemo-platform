// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { Dial } from '@nemo/common/src/components/Dial';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useJobsCancelJob } from '@nemo/sdk/generated/platform/api';
import {
  getSafeSynthesizerDownloadJobResultSummaryQueryOptions as getDownloadJobResultSummaryQueryOptions,
  getSafeSynthesizerListJobsQueryKey,
  useSafeSynthesizerListJobs,
} from '@nemo/sdk/generated/safe-synthesizer/api';
import {
  SafeSynthesizerJob,
  SafeSynthesizerJobsListFilter,
  SafeSynthesizerJobsSortField,
} from '@nemo/sdk/generated/safe-synthesizer/schema';
import { Banner, Button, Stack } from '@nvidia/foundations-react-core';
import { DeleteJobModal } from '@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal';
import { isCancellableJob } from '@studio/components/dataViews/SafeSynthesizerJobsDataView/utils';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { FilesetFilePreviewLink } from '@studio/components/SafeSynthesizerFilesetPreview/FilesetFilePreviewLink';
import { LINK_DOCS_SAFE_SYNTHESIZER } from '@studio/constants/links';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  getNewSafeSynthesizerRoute,
  getSafeSynthesizerJobReportRoute,
  getSafeSynthesizerJobRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useQueries, useQueryClient } from '@tanstack/react-query';
import { ShieldCheck, Trash } from 'lucide-react';
import { ComponentProps, FC, useCallback, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

type SafeSynthesizerJobWithId = SafeSynthesizerJob & { id: string };

export const SafeSynthesizerJobsDataView: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const [deleteJobs, setDeleteJobs] = useState<SafeSynthesizerJob[]>([]);
  const [cancelError, setCancelError] = useState<string | undefined>(undefined);

  // Cancel job mutation
  const cancelJobMutation = useJobsCancelJob({
    mutation: {
      onSuccess: () => {
        queryClient.resetQueries({
          queryKey: getSafeSynthesizerListJobsQueryKey(workspace),
        });
        setCancelError(undefined);
      },
      onError: (error) => {
        setCancelError(error instanceof Error ? error.message : 'Failed to cancel job');
      },
    },
  });

  const handleCancelJob = useCallback(
    async (job: SafeSynthesizerJob) => {
      if (job.workspace && job.name) {
        try {
          setCancelError(undefined);
          await cancelJobMutation.mutateAsync({ workspace: job.workspace, name: job.name });
        } catch {
          // Error is handled by onError callback
        }
      }
    },
    [cancelJobMutation]
  );

  // Fetch jobs using dataViewState for pagination, sorting, search, and filters
  const { data: safeSynthesizerResponse, isLoading } = useSafeSynthesizerListJobs(
    workspace,
    {
      sort: getSortParam(dataViewState.sorting.state) as SafeSynthesizerJobsSortField,
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      filter: {
        ...((dataViewState.apiFilter.filter ?? {}) as SafeSynthesizerJobsListFilter),
        ...(dataViewState.apiFilter.searchText
          ? withOperators<SafeSynthesizerJobsListFilter>({
              name: { $like: dataViewState.apiFilter.searchText },
            })
          : {}),
      },
    },
    {
      query: {
        placeholderData: keepPreviousData,
        refetchInterval: JOB_POLLING_INTERVAL_MS,
        refetchOnMount: 'always',
      },
    }
  );

  // Filter jobs with valid IDs for summary queries
  const jobsWithIds = useMemo(
    () =>
      (safeSynthesizerResponse?.data || []).filter(
        (row): row is SafeSynthesizerJobWithId => row.id !== undefined
      ),
    [safeSynthesizerResponse?.data]
  );

  // Fetch summary data for each row that has completed status
  const summaryQueries = useQueries({
    queries:
      safeSynthesizerResponse?.data
        .filter((row) => row.name !== undefined && row.workspace !== undefined)
        .map((row) =>
          getDownloadJobResultSummaryQueryOptions(row.workspace!, row.name!, {
            query: {
              enabled: row.status === 'completed',
              staleTime: 10 * 60 * 1000, // 10 minutes
              gcTime: 10 * 60 * 1000, // 10 minutes
            },
          })
        ) ?? [],
  });

  // Ensure each job has a unique id for DataView row selection
  const jobs = useMemo<SafeSynthesizerJobWithId[]>(
    () =>
      (safeSynthesizerResponse?.data || []).map((job) => ({
        ...job,
        id: job.id || `${job.workspace}/${job.name}`,
      })),
    [safeSynthesizerResponse?.data]
  );

  // Create a map of job id to summary query index for efficient lookup
  const summaryDataMap = useMemo(() => {
    const map = new Map<string, number>();
    jobsWithIds.forEach((row, index) => {
      map.set(row.id, index);
    });
    return map;
  }, [jobsWithIds]);

  const hasActiveFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;

  // Column definitions
  const makeColumns: ComponentProps<
    typeof StudioDataView<SafeSynthesizerJobWithId>
  >['makeColumns'] = useCallback(
    ({ accessor }, { rowSelectionColumn, rowActionsColumn }) => [
      rowSelectionColumn({
        size: ROW_SELECTION_COLUMN_SIZE,
      }),
      accessor('name', {
        header: 'Name',
      }),
      {
        id: 'fileset',
        header: 'Dataset',
        cell: ({ row }: { row: DataView.TanstackTable.Row<SafeSynthesizerJobWithId> }) => (
          <FilesetFilePreviewLink url={row.original.spec?.data_source as string}>
            <span className="truncate font-semibold text-sm">
              {row.original.spec?.data_source as string}
            </span>
          </FilesetFilePreviewLink>
        ),
      },
      {
        id: 'sqs',
        header: () => (
          <abbr title="Synthetic Quality Score" className="no-underline">
            SQS
          </abbr>
        ),
        size: 70,
        cell: ({ row }: { row: DataView.TanstackTable.Row<SafeSynthesizerJobWithId> }) => {
          const summaryIndex = summaryDataMap.get(row.original.id);
          const summaryData =
            summaryIndex !== undefined ? summaryQueries[summaryIndex]?.data : undefined;
          const sqsValue = summaryData?.synthetic_data_quality_score
            ? (summaryData.synthetic_data_quality_score / 10) * 100
            : 0;
          const sqsDisplay = summaryData?.synthetic_data_quality_score
            ? summaryData.synthetic_data_quality_score.toFixed(1)
            : '';
          return (
            <Link
              to={getSafeSynthesizerJobReportRoute(workspace, row.original.name!)}
              className="flex items-center"
              aria-label={`View SQS for job ${row.original.name}`}
            >
              <Dial
                value={sqsValue}
                displayValue={sqsDisplay}
                color="var(--color-purple-500)"
                size="s"
              />
            </Link>
          );
        },
      },
      {
        id: 'dps',
        header: () => (
          <abbr title="Data Privacy Score" className="no-underline">
            DPS
          </abbr>
        ),
        size: 70,
        cell: ({ row }: { row: DataView.TanstackTable.Row<SafeSynthesizerJobWithId> }) => {
          const summaryIndex = summaryDataMap.get(row.original.id);
          const summaryData =
            summaryIndex !== undefined ? summaryQueries[summaryIndex]?.data : undefined;
          const dpsValue = summaryData?.data_privacy_score
            ? (summaryData.data_privacy_score / 10) * 100
            : 0;
          const dpsDisplay = summaryData?.data_privacy_score
            ? summaryData.data_privacy_score.toFixed(1)
            : '';
          return (
            <Link
              to={getSafeSynthesizerJobReportRoute(workspace, row.original.name!)}
              className="flex items-center"
              aria-label={`View DPS for job ${row.original.name}`}
            >
              <Dial
                value={dpsValue}
                displayValue={dpsDisplay}
                color="var(--color-blue-500)"
                size="s"
              />
            </Link>
          );
        },
      },
      accessor('created_at', {
        id: 'created_at',
        header: 'Created',
        enableSorting: true,
        size: 150,
        meta: {
          filter: dateTimeFilter('Created At'),
        },
        cell: ({ row }) =>
          row.original.created_at ? <RelativeTime datetime={row.original.created_at} /> : null,
      }),
      accessor('status', {
        header: 'Status',
        size: 125,
        meta: {
          filter: {
            type: 'single-select' as const,
            label: 'Status',
            options: STATUS_FILTER_OPTIONS,
          },
        },
        cell: ({ row }) =>
          row.original.status ? <StatusBadge status={row.original.status} /> : null,
      }),
      rowActionsColumn({
        size: ROW_ACTIONS_COLUMN_SIZE,
        enableResizing: false,
        cell: ({ row }) => (
          <QuickActionsMenuRoot
            actions={[
              {
                label: 'View Summary',
                onSelect: () => {
                  if (row.original.name) {
                    navigate(getSafeSynthesizerJobRoute(workspace, row.original.name));
                  }
                },
              },
              ...(row.original.status === 'completed'
                ? [
                    {
                      label: 'View Report',
                      onSelect: () => {
                        if (row.original.name) {
                          navigate(getSafeSynthesizerJobReportRoute(workspace, row.original.name));
                        }
                      },
                    },
                  ]
                : []),
              {
                label: 'Delete',
                onSelect: () => setDeleteJobs([row.original]),
              },
              ...(isCancellableJob(row.original.status)
                ? [
                    {
                      label: 'Cancel',
                      onSelect: () => handleCancelJob(row.original),
                    },
                  ]
                : []),
            ]}
          />
        ),
      }),
    ],
    [handleCancelJob, navigate, summaryDataMap, summaryQueries, workspace]
  );

  const totalResults = safeSynthesizerResponse?.pagination?.total_results ?? 0;

  return (
    <Stack className="flex-1 min-h-0">
      {cancelError && (
        <Banner kind="inline" status="error">
          {cancelError}
        </Banner>
      )}

      <StudioDataView<SafeSynthesizerJobWithId>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={(row: SafeSynthesizerJobWithId) => {
          if (row.name) {
            navigate(getSafeSynthesizerJobRoute(workspace, row.name));
          }
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
            placeholder: 'Search Jobs...',
          },
          DataViewRoot: {
            data: jobs,
            totalCount: totalResults,
            requestStatus: isLoading && !safeSynthesizerResponse ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No jobs match your search criteria"
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="Generate Safe Synthetic Data"
                  emptyMessage="Create a private version of a sensitive tabular dataset."
                  icon={<ShieldCheck className="size-12" />}
                  actions={
                    <>
                      <DocumentationButton href={LINK_DOCS_SAFE_SYNTHESIZER} />
                      <Button asChild color="brand">
                        <Link to={getNewSafeSynthesizerRoute(workspace)}>Synthesize Data</Link>
                      </Button>
                    </>
                  }
                />
              ),
          },
        }}
      />

      {deleteJobs.length > 0 && (
        <DeleteJobModal
          jobs={deleteJobs}
          onClose={() => {
            setDeleteJobs([]);
            dataViewState.rowSelection.set({});
          }}
        />
      )}
    </Stack>
  );
};
