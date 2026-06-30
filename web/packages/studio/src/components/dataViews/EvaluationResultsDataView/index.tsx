// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import { useEvaluatorListEvaluateJobs } from '@nemo/sdk/generated/evaluator/api';
import {
  type EvaluateJob,
  type EvaluateJobsListFilter,
  EvaluateJobsSortField,
} from '@nemo/sdk/generated/evaluator/schema';
import { Button, Flex, StatusMessage } from '@nvidia/foundations-react-core';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { LINK_DOCS_STUDIO_EVALUATION } from '@studio/constants/links';
import { STATUS_FILTER_OPTIONS } from '@studio/constants/platformJobs';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getEvaluationResultDetailsRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { ListChecks } from 'lucide-react';
import { ComponentProps } from 'react';
import { useNavigate } from 'react-router-dom';

const STATUS_OPTIONS_WITH_ALL = [{ value: '', label: 'All' }, ...STATUS_FILTER_OPTIONS];

const SORTABLE_FIELDS = Object.values(EvaluateJobsSortField).filter((v) => !v.startsWith('-'));
const DEFAULT_SORT = EvaluateJobsSortField['-created_at'];

export const EvaluationResultsDataView = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  const dataViewState = useStudioDataViewState<EvaluateJobsListFilter>({
    defaultSort: { id: 'created_at', desc: true },
  });

  const {
    data: jobsData,
    isFetching,
    error,
  } = useEvaluatorListEvaluateJobs(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: getSortParamWithWhitelist(
        dataViewState.sorting.state,
        SORTABLE_FIELDS,
        DEFAULT_SORT
      ) as EvaluateJobsSortField,
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.apiFilter.searchText
          ? withOperators<EvaluateJobsListFilter>({
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

  const jobs = jobsData?.data ?? [];

  const makeColumns: ComponentProps<typeof StudioDataView<EvaluateJob>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor((original) => original?.name || '', {
      id: 'name',
      header: 'Name',
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

  const hasActiveFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;
  const isInitialEmpty = jobs.length === 0 && !isFetching && !error && !hasActiveFilters;

  if (error) {
    return (
      <TableEmptyState
        header="Failed to fetch evaluations"
        emptyMessage="An error occurred while loading evaluation jobs."
      />
    );
  }

  return (
    <StudioDataView<EvaluateJob>
      dataViewState={dataViewState}
      searchField="name"
      makeColumns={makeColumns}
      onRowClick={(row) => {
        if (!row.name) return;
        navigate(getEvaluationResultDetailsRoute(workspace, row.name));
      }}
      attributes={{
        DataViewSearchBar: {
          placeholder: 'Search by name',
        },
        DataViewRoot: {
          data: jobs,
          totalCount: jobsData?.pagination?.total_results ?? 0,
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
                  slotHeading="Manage Evaluations"
                  slotSubheading="Refine and optimize your large language models (LLMs) for enhanced performance and real-world applicability."
                  slotMedia={<ListChecks className="size-12" />}
                  slotFooter={
                    <Flex gap="density-md" justify="center">
                      <DocumentationButton href={LINK_DOCS_STUDIO_EVALUATION} />
                    </Flex>
                  }
                />
              </Flex>
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
  );
};
