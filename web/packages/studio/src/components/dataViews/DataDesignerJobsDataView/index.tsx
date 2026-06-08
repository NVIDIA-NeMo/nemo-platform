// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { CJobCancellableStatuses } from '@nemo/common/src/constants/query';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import {
  getDataDesignerListCreateJobsQueryKey,
  useDataDesignerCancelCreateJob,
  useDataDesignerListCreateJobs,
} from '@nemo/sdk/generated/data-designer/api';
import type {
  CreateJob as DataDesignerJob,
  CreateJobsListFilter as DataDesignerJobsListFilter,
  CreateJobsSortField as DataDesignerJobsSortField,
} from '@nemo/sdk/generated/data-designer/schema';
import { Banner, Button, Text } from '@nvidia/foundations-react-core';
import { DeleteJobModal } from '@studio/components/dataViews/DataDesignerJobsDataView/DeleteJobModal';
import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getDataDesignerJobDetailsRoute, getNewDataDesignerJobRoute } from '@studio/routes/utils';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { Trash } from 'lucide-react';
import { ComponentProps, FC, useCallback, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

type DataDesignerJobWithId = DataDesignerJob & { id: string };

export const DataDesignerJobsDataView: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
    columnVisibility: { updated_at: false },
  });

  const [deleteJobs, setDeleteJobs] = useState<DataDesignerJob[]>([]);
  const [cancelError, setCancelError] = useState<string | undefined>(undefined);

  const cancelJobMutation = useDataDesignerCancelCreateJob({
    mutation: {
      onSuccess: () => {
        queryClient.resetQueries({
          queryKey: getDataDesignerListCreateJobsQueryKey(workspace),
        });
        setCancelError(undefined);
      },
      onError: (error) => {
        setCancelError(error instanceof Error ? error.message : 'Failed to cancel job');
      },
    },
  });

  const handleCancelJob = useCallback(
    async (job: DataDesignerJob) => {
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

  const { data: dataDesignerResponse, isLoading } = useDataDesignerListCreateJobs(
    workspace,
    {
      sort: getSortParam(dataViewState.sorting.state) as DataDesignerJobsSortField,
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      filter: {
        ...((dataViewState.apiFilter.filter ?? {}) as DataDesignerJobsListFilter),
        ...(dataViewState.apiFilter.searchText
          ? withOperators<DataDesignerJobsListFilter>({
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

  const jobs = useMemo<DataDesignerJobWithId[]>(
    () =>
      (dataDesignerResponse?.data || []).map((job) => ({
        ...job,
        id: job.id || `${job.workspace ?? ''}/${job.name}`,
      })),
    [dataDesignerResponse?.data]
  );

  const hasActiveFilters =
    Boolean(dataViewState.debouncedSearchBar) || dataViewState.debouncedColumnFilters.length > 0;

  const resetFilters = useCallback(() => {
    dataViewState.resetFilters();
  }, [dataViewState]);

  const makeColumns: ComponentProps<typeof StudioDataView<DataDesignerJobWithId>>['makeColumns'] = (
    { accessor },
    { rowSelectionColumn, rowActionsColumn }
  ) => [
    rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
    accessor('name', {
      header: 'Name',
      cell: ({ row }) => row.original.name,
    }),
    accessor('description', {
      header: 'Description',
      cell: ({ row }) => (
        <Text className="max-w-[200px] truncate" kind="body/regular/md">
          {row.original.description ?? '-'}
        </Text>
      ),
    }),
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
    accessor('updated_at', {
      id: 'updated_at',
      header: 'Updated',
      enableSorting: false,
      meta: {
        filter: dateTimeFilter('Updated At'),
      },
      cell: ({ row }) =>
        row.original?.updated_at ? <RelativeTime datetime={row.original.updated_at} /> : null,
    }),
    rowActionsColumn({
      size: 70,
      enableResizing: false,
      cell: ({ row }) => (
        <QuickActionsMenuRoot
          actions={[
            {
              label: 'View details',
              onSelect: () => {
                if (row.original.name) {
                  navigate(getDataDesignerJobDetailsRoute(workspace, row.original.name));
                }
              },
            },
            {
              label: 'Delete',
              onSelect: () => setDeleteJobs([row.original]),
            },
            ...(row.original.status && CJobCancellableStatuses.includes(row.original.status)
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
  ];

  const totalResults = dataDesignerResponse?.pagination?.total_results ?? 0;

  return (
    <>
      {cancelError && (
        <Banner kind="inline" status="error">
          {cancelError}
        </Banner>
      )}

      <StudioDataView<DataDesignerJobWithId>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={(row) => navigate(getDataDesignerJobDetailsRoute(workspace, row.name))}
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
            placeholder: 'Search jobs...',
          },
          DataViewRoot: {
            data: jobs,
            totalCount: totalResults,
            requestStatus: isLoading && !dataDesignerResponse ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No jobs match your search criteria"
                  actions={
                    <Button kind="tertiary" onClick={resetFilters}>
                      Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="Data Designer Jobs"
                  emptyMessage="Create and manage data designer jobs to generate or transform datasets."
                  actions={
                    <Button asChild color="brand">
                      <Link to={getNewDataDesignerJobRoute(workspace)}>New Job</Link>
                    </Button>
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
    </>
  );
};
