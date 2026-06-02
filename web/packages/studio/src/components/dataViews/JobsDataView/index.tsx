// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParam } from '@nemo/common/src/utils/query';
import { useJobsListJobs } from '@nemo/sdk/generated/platform/api';
import type {
  PlatformJobResponse,
  PlatformJobSortField,
  PlatformJobsListFilter,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, StatusMessage } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { CancelJobButton } from '@studio/components/CancelJobButton';
import {
  HIDDEN_JOB_SOURCES,
  JOB_SOURCE,
  SOURCE_OPTIONS,
} from '@studio/components/dataViews/JobsDataView/constants';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import {
  CUSTOMIZER_ENABLED,
  DATA_DESIGNER_ENABLED,
  EVALUATOR_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
} from '@studio/constants/environment';
import { LINK_DOCS_JOBS } from '@studio/constants/links';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { iconColorClass } from '@studio/routes/constants';
import {
  getDataDesignerJobDetailsRoute,
  getEvaluationResultDetailsRoute,
  getSafeSynthesizerJobRoute,
  getWorkspaceCustomizationJobDetailsRoute,
  getWorkspaceJobDetailRoute,
} from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { ChartBar, Cog, LayoutList, ListChecks, Sliders, Sparkles } from 'lucide-react';
import { ComponentProps, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

const SOURCE_DISPLAY: Record<string, { label: string; icon: ReactNode }> = {
  [JOB_SOURCE.CUSTOMIZATION]: {
    label: 'Customizer',
    icon: <Sliders className={iconColorClass} size={14} />,
  },
  [JOB_SOURCE.DATA_DESIGNER]: {
    label: 'Data Designer',
    icon: <LayoutList className={iconColorClass} size={14} />,
  },
  [JOB_SOURCE.SAFE_SYNTHESIZER]: {
    label: 'Safe Synthesizer',
    icon: <Sparkles className={iconColorClass} size={14} />,
  },
  [JOB_SOURCE.EVALUATOR_METRICS]: {
    label: 'Evaluator',
    icon: <ChartBar className={iconColorClass} size={14} />,
  },
};

const STATUS_OPTIONS_WITH_ALL = [{ value: '', label: 'All' }, ...STATUS_FILTER_OPTIONS];

const SOURCE_DETAIL_ROUTE: Record<
  string,
  { enabled: boolean; getRoute: (workspace: string, jobName: string) => string }
> = {
  [JOB_SOURCE.CUSTOMIZATION]: {
    enabled: CUSTOMIZER_ENABLED,
    getRoute: getWorkspaceCustomizationJobDetailsRoute,
  },
  [JOB_SOURCE.DATA_DESIGNER]: {
    enabled: DATA_DESIGNER_ENABLED,
    getRoute: getDataDesignerJobDetailsRoute,
  },
  [JOB_SOURCE.SAFE_SYNTHESIZER]: {
    enabled: SAFE_SYNTHESIZER_ENABLED,
    getRoute: getSafeSynthesizerJobRoute,
  },
  [JOB_SOURCE.EVALUATOR_METRICS]: {
    enabled: EVALUATOR_ENABLED,
    getRoute: getEvaluationResultDetailsRoute,
  },
};

const getJobDetailRoute = (job: PlatformJobResponse, workspace: string): string => {
  const genericRoute = getWorkspaceJobDetailRoute(workspace, job.name);
  const entry = job.source ? SOURCE_DETAIL_ROUTE[job.source] : undefined;
  return entry?.enabled ? entry.getRoute(workspace, job.name) : genericRoute;
};

export const JobsDataView = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const userFilter = { ...(dataViewState.apiFilter.filter ?? {}) };
  if (!CUSTOMIZER_ENABLED && userFilter.source === JOB_SOURCE.CUSTOMIZATION) {
    delete userFilter.source;
  }

  const hiddenJobSources = CUSTOMIZER_ENABLED
    ? HIDDEN_JOB_SOURCES
    : [...HIDDEN_JOB_SOURCES, JOB_SOURCE.CUSTOMIZATION];
  const sourceFilterOptions = SOURCE_OPTIONS.filter(
    (option) => CUSTOMIZER_ENABLED || option.value !== JOB_SOURCE.CUSTOMIZATION
  );
  const hasUserSourceFilter = userFilter.source !== undefined && userFilter.source !== '';

  const {
    data: jobsData,
    isFetching,
    error,
  } = useJobsListJobs(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParam(dataViewState.sorting.state) as PlatformJobSortField,
      filter: {
        ...userFilter,
        ...(hasUserSourceFilter
          ? {}
          : withOperators<PlatformJobsListFilter>({ source: { $nin: hiddenJobSources } })),
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
        staleTime: 0,
        refetchOnWindowFocus: true,
      },
    }
  );

  const jobs =
    CUSTOMIZER_ENABLED || !jobsData?.data
      ? (jobsData?.data ?? [])
      : jobsData.data.filter((job) => job.source !== JOB_SOURCE.CUSTOMIZATION);

  const makeColumns: ComponentProps<typeof StudioDataView<PlatformJobResponse>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor((original) => original?.name || '', {
      id: 'name',
      header: 'Name',
    }),
    accessor((original) => original?.source || '', {
      id: 'source',
      header: 'Source',
      size: 200,
      meta: {
        filter: {
          type: 'single-select' as const,
          label: 'Source',
          options: sourceFilterOptions,
        },
      },
      cell: ({ row, column: col }) => {
        const sourceValue = row.original.source;
        if (!sourceValue) return '-';
        const display = SOURCE_DISPLAY[sourceValue];
        const icon = display?.icon ?? <Cog className={iconColorClass} size={14} />;
        const label = display?.label ?? sourceValue;
        return (
          <Flex
            align="center"
            gap="density-sm"
            className="cursor-pointer"
            data-no-row-click
            onClick={() => col.setFilterValue(sourceValue)}
          >
            {icon}
            {label}
          </Flex>
        );
      },
    }),
    accessor((original) => original?.status || '', {
      id: 'status',
      header: 'Status',
      size: 150,
      meta: {
        filter: {
          type: 'single-select' as const,
          label: 'Status',
          options: STATUS_OPTIONS_WITH_ALL,
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
    accessor(() => '', {
      id: 'actions',
      header: '',
      size: 120,
      enableSorting: false,
      cell: ({ row }) => (
        <Flex justify="end">
          <CancelJobButton jobName={row.original.name} jobStatus={row.original.status} compact />
        </Flex>
      ),
    }),
  ];

  const hasActiveFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;
  const isInitialEmpty = jobs.length === 0 && !isFetching && !error && !hasActiveFilters;

  if (error) {
    return <ErrorPanel errorMessage={getErrorMessage(error)} />;
  }

  return (
    <StudioDataView<PlatformJobResponse>
      dataViewState={dataViewState}
      searchField="name"
      makeColumns={makeColumns}
      onRowClick={(row: PlatformJobResponse) => {
        navigate(getJobDetailRoute(row, workspace));
      }}
      attributes={{
        DataViewSearchBar: {
          placeholder: 'Search by name',
        },
        DataViewRoot: {
          data: jobs,
          totalCount: CUSTOMIZER_ENABLED ? jobsData?.pagination?.total_results || 0 : jobs.length,
          requestStatus: isFetching ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () =>
            isInitialEmpty ? (
              <Flex
                justify="center"
                align="center"
                className="h-full min-h-[min(480px,60vh)] w-full py-density-3xl"
              >
                <StatusMessage
                  className="max-w-lg"
                  size="medium"
                  slotHeading="Manage Jobs"
                  slotSubheading="Manage and monitor your NeMo Platform jobs with full visibility into every run. One hub for all your NeMo Platform jobs — configure, manage, and monitor with ease."
                  slotMedia={<ListChecks className="size-12" />}
                  slotFooter={
                    <Flex gap="density-md" justify="center">
                      <Button
                        kind="tertiary"
                        onClick={() => window.open(LINK_DOCS_JOBS, '_blank', 'noopener,noreferrer')}
                      >
                        Documentation
                      </Button>
                    </Flex>
                  }
                />
              </Flex>
            ) : (
              <TableEmptyState
                header="No Results Found"
                emptyMessage="No jobs match your search or filters."
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
  );
};
