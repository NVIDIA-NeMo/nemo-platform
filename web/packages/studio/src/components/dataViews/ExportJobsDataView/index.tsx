// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useListExportJobs } from '@nemo/sdk/generated/platform/api';
import type {
  ExportJob,
  ExportJobFilter,
  ExportJobSortField,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { ExportJobPanel } from '@studio/components/sidePanels/ExportJobPanel';
import { EXPORT_JOB_STATUS_FILTER_OPTIONS } from '@studio/constants/intakeJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { keepPreviousData } from '@tanstack/react-query';
import { Database } from 'lucide-react';
import { ComponentProps } from 'react';

export const ExportJobsDataView = () => {
  const workspace = useWorkspaceFromPath();
  const { getQueryParam, setQueryParam } = useQueryParams();
  const exportJobId = getQueryParam(QUERY_PARAMETERS.exportJobId);

  const dataViewState = useStudioDataViewState<ExportJobFilter>({
    defaultSort: { id: 'created_at', desc: true },
  });

  const hasActiveFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;

  const {
    data: exportJobsData,
    isFetching: isFetchingExportJobs,
    error,
  } = useListExportJobs(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParam(dataViewState.sorting.state) as ExportJobSortField,
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.apiFilter.searchText ? { id: dataViewState.apiFilter.searchText } : {}),
      },
    },
    {
      query: {
        placeholderData: keepPreviousData,
        // eagerly refetch so user can always see up to date job statuses
        staleTime: 0,
        refetchOnWindowFocus: true,
      },
    }
  );

  const makeColumns: ComponentProps<typeof StudioDataView<ExportJob>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor((original) => original?.id || '', {
      header: 'Job ID',
      cell: ({ row }) => row.original.id,
    }),
    accessor((original) => original?.output_file_url || '', {
      header: 'Destination',
      cell: ({ row }) => (
        <Flex align="center" gap="1">
          <Database className="flex-none" />
          {row.original.output_file_url}
        </Flex>
      ),
    }),
    accessor((original) => original?.status || '', {
      header: 'Status',
      size: 125,
      meta: {
        filter: {
          type: 'single-select' as const,
          label: 'Status',
          options: EXPORT_JOB_STATUS_FILTER_OPTIONS,
        },
      },
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    }),
    accessor((original) => original?.created_at || '', {
      id: 'created_at',
      header: 'Created',
      size: 200,
      enableSorting: true,
      meta: {
        filter: dateTimeFilter('Created At'),
      },
      cell: ({ row }) => <RelativeTime datetime={row.original.created_at ?? ''} />,
    }),
  ];

  // Error state
  if (error) {
    return <ErrorPanel errorMessage={getErrorMessage(error)} />;
  }

  return (
    <Stack className="flex-1 min-h-0">
      <StudioDataView
        dataViewState={dataViewState}
        searchField="id"
        makeColumns={makeColumns}
        onRowClick={(row) => {
          if (row.id) {
            setQueryParam(QUERY_PARAMETERS.exportJobId, row.id);
          }
        }}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search by job ID',
          },
          DataViewRoot: {
            data: exportJobsData?.data || [],
            totalCount: exportJobsData?.pagination?.total_results || 0,
            requestStatus: isFetchingExportJobs ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No export jobs match your filters"
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Filters
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  header="No Export Jobs"
                  emptyMessage="Export jobs will appear here once created."
                />
              ),
          },
        }}
      />
      <ExportJobPanel
        exportJobId={exportJobId}
        attributes={{
          SidePanel: {
            open: !!exportJobId,
            onOpenChange: (open) => {
              if (!open) {
                setQueryParam(QUERY_PARAMETERS.exportJobId, '');
              }
            },
          },
        }}
      />
    </Stack>
  );
};
