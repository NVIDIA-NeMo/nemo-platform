// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import {
  type QuickActionItem,
  QuickActionsMenuRoot,
} from '@nemo/common/src/components/QuickActionsMenu/QuickActionsMenuRoot';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import {
  getDataDesignerListCreateJobsQueryKey,
  useDataDesignerDeleteCreateJob,
} from '@nemo/sdk/generated/data-designer/api';
import type { CreateJob as DataDesignerCreateJob } from '@nemo/sdk/generated/data-designer/schema';
import { getJobsListJobsQueryKey, useJobsListJobs } from '@nemo/sdk/generated/platform/api';
import type {
  PlatformJobListSortField,
  PlatformJobResponse,
  PlatformJobsListFilter,
} from '@nemo/sdk/generated/platform/schema';
import { Banner, Button, Text } from '@nvidia/foundations-react-core';
import { BulkDeleteModal } from '@studio/components/BulkDeleteModal';
import { DataDesignerJobActionsMenu } from '@studio/components/DataDesignerJobActionsMenu';
import { DataDesignerIconFc } from '@studio/constants/constants';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  getDataDesignerJobDetailsRoute,
  getFilesetRoute,
  getNewDataDesignerJobRoute,
  getWorkspaceJobDetailRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { Trash } from 'lucide-react';
import { ComponentProps, FC, useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router';

const LEGACY_DATA_DESIGNER_SOURCE = 'data-designer';
const DATA_DESIGNER_CREATE_SOURCE = 'nemo-data-designer-plugin';
const DATASET_BUILD_SOURCE = 'nemo-data-designer.build-dataset';
const DATA_DESIGNER_JOB_SOURCES = [
  LEGACY_DATA_DESIGNER_SOURCE,
  DATA_DESIGNER_CREATE_SOURCE,
  DATASET_BUILD_SOURCE,
];

const isCreateJob = (job: PlatformJobResponse) =>
  job.source === LEGACY_DATA_DESIGNER_SOURCE || job.source === DATA_DESIGNER_CREATE_SOURCE;

const isDatasetBuildJob = (job: PlatformJobResponse) => job.source === DATASET_BUILD_SOURCE;

const getDatasetDestination = (job: PlatformJobResponse): string | undefined => {
  if (!isDatasetBuildJob(job)) return undefined;
  const destination = job.spec?.destination;
  if (!destination || typeof destination !== 'object' || Array.isArray(destination))
    return undefined;
  const name = (destination as Record<string, unknown>).name;
  return typeof name === 'string' && name.length > 0 ? name : undefined;
};

export const DataDesignerJobsDataView: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();

  const dataViewState = useStudioDataViewState<PlatformJobsListFilter>({
    defaultSort: [{ id: 'created_at', desc: true }],
    columnVisibility: { updated_at: false },
  });

  const queryClient = useQueryClient();

  const [deleteJobs, setDeleteJobs] = useState<PlatformJobResponse[]>([]);
  const [cancelError, setCancelError] = useState<string | undefined>(undefined);

  const deleteJobMutation = useDataDesignerDeleteCreateJob({
    mutation: {
      onSuccess: () => {
        queryClient.resetQueries({
          queryKey: getDataDesignerListCreateJobsQueryKey(workspace),
        });
        queryClient.resetQueries({
          queryKey: getJobsListJobsQueryKey(workspace),
        });
      },
    },
  });

  const handleDeleteJobs = async (jobsToDelete: PlatformJobResponse[]) => {
    const invalid = jobsToDelete.filter((job) => !isCreateJob(job) || !job.workspace || !job.name);
    if (invalid.length > 0) {
      throw new Error(
        `Cannot delete ${invalid.length} job${invalid.length !== 1 ? 's' : ''}: unsupported job type or missing workspace/name.`
      );
    }
    await Promise.all(
      jobsToDelete.map(async (job) => {
        try {
          await deleteJobMutation.mutateAsync({ workspace: job.workspace, name: job.name });
        } catch (error) {
          throw new Error(
            `Failed to delete job "${job.name}": ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      })
    );
  };

  const {
    data: dataDesignerResponse,
    isFetching,
    error,
  } = useJobsListJobs(
    workspace,
    {
      sort: getSortParam(dataViewState.sorting.state) as PlatformJobListSortField,
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      filter: {
        ...(dataViewState.apiFilter.filter ?? {}),
        ...withOperators<PlatformJobsListFilter>({
          source: { $in: DATA_DESIGNER_JOB_SOURCES },
        }),
        ...(dataViewState.apiFilter.searchText
          ? withOperators<PlatformJobsListFilter>({
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

  const jobs = dataDesignerResponse?.data ?? [];

  const hasActiveFilters =
    Boolean(dataViewState.debouncedSearchBar) || dataViewState.debouncedColumnFilters.length > 0;

  const resetFilters = useCallback(() => {
    dataViewState.resetFilters();
  }, [dataViewState]);

  const getBuildJobActions = (job: PlatformJobResponse): QuickActionItem[] => {
    const destination = getDatasetDestination(job);
    return [
      {
        label: 'View job details',
        onSelect: () => navigate(getWorkspaceJobDetailRoute(workspace, job.name)),
      },
      ...(destination
        ? [
            {
              label: 'View output dataset',
              onSelect: () => navigate(getFilesetRoute(workspace, destination)),
            },
          ]
        : []),
    ];
  };

  const makeColumns: ComponentProps<typeof StudioDataView<PlatformJobResponse>>['makeColumns'] = (
    { accessor },
    { rowSelectionColumn, rowActionsColumn }
  ) => [
    rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
    accessor('name', {
      header: 'Name',
      cell: ({ row }) => row.original.name,
    }),
    accessor('source', {
      header: 'Type',
      size: 150,
      cell: ({ row }) => (isDatasetBuildJob(row.original) ? 'Dataset build' : 'Data generation'),
    }),
    accessor('description', {
      header: 'Description',
      cell: ({ row }) => (
        <Text className="max-w-[200px] truncate" kind="body/regular/md">
          {row.original.description ?? '-'}
        </Text>
      ),
    }),
    accessor((job) => getDatasetDestination(job) ?? '', {
      id: 'output_dataset',
      header: 'Output Dataset',
      enableSorting: false,
      cell: ({ row }) => {
        const destination = getDatasetDestination(row.original);
        return destination ? (
          <Link data-no-row-click to={getFilesetRoute(workspace, destination)}>
            {destination}
          </Link>
        ) : (
          '-'
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
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    }),
    accessor('updated_at', {
      id: 'updated_at',
      header: 'Updated',
      enableSorting: false,
      meta: {
        filter: dateTimeFilter('Updated At'),
      },
      cell: ({ row }) =>
        row.original.updated_at ? <RelativeTime datetime={row.original.updated_at} /> : null,
    }),
    rowActionsColumn({
      size: 70,
      enableResizing: false,
      cell: ({ row }) =>
        isCreateJob(row.original) ? (
          <DataDesignerJobActionsMenu
            job={row.original as unknown as DataDesignerCreateJob}
            includeViewDetails
            onCancelError={setCancelError}
          />
        ) : (
          <QuickActionsMenuRoot actions={getBuildJobActions(row.original)} />
        ),
    }),
  ];

  const totalResults = dataDesignerResponse?.pagination?.total_results ?? 0;

  if (error) {
    return <ErrorPanel errorMessage={getErrorMessage(error)} />;
  }

  return (
    <>
      {cancelError && (
        <Banner kind="inline" status="error">
          {cancelError}
        </Banner>
      )}

      <StudioDataView<PlatformJobResponse>
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={(row) =>
          navigate(
            isDatasetBuildJob(row)
              ? getWorkspaceJobDetailRoute(workspace, row.name)
              : getDataDesignerJobDetailsRoute(workspace, row.name)
          )
        }
        renderBulkActions={({ selectedRows }) => (
          <Button
            kind="tertiary"
            aria-label="Delete selected jobs"
            onClick={() => setDeleteJobs(selectedRows.filter(isCreateJob))}
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
            requestStatus: isFetching && !dataDesignerResponse ? 'loading' : undefined,
            reactTableOptions: {
              enableRowSelection: (row) => isCreateJob(row.original),
            },
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
                  icon={<DataDesignerIconFc className="h-[64px] w-[64px]" />}
                  header="Data Designer Jobs"
                  emptyMessage="Create and manage data generation and dataset build jobs."
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

      <BulkDeleteModal
        items={deleteJobs}
        open={deleteJobs.length > 0}
        onDelete={handleDeleteJobs}
        title={(count) => `Delete ${count} Data Designer Job${count !== 1 ? 's' : ''}`}
        onClose={() => {
          setDeleteJobs([]);
          dataViewState.rowSelection.set({});
        }}
      />
    </>
  );
};
