// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { WithFilterOperators } from '@nemo/common/src/api/filterOperators';
import {
  dateTimeFilter,
  type DatetimeFilterValue,
} from '@nemo/common/src/components/DataView/dateTimeFilter';
import * as DataView from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { DEFAULT_PAGE_SIZE_OPTIONS } from '@nemo/common/src/constants/pagination';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useListExperiments } from '@nemo/sdk/generated/platform/api';
import type {
  ExperimentFilter,
  ExperimentResponse,
} from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Button,
  Flex,
  PageHeader,
  PaginationArrowButton,
  PaginationControlsGroup,
  PaginationDivider,
  PaginationItemRangeText,
  PaginationNavigationGroup,
  PaginationPageCountText,
  PaginationPageInput,
  PaginationPageSizeSelect,
  Stack,
  StatusMessage,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ExperimentCreateModal } from '@studio/components/ExperimentCreateModal';
import { FeatureFlagBadge } from '@studio/components/FeatureFlagBadge';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentCard } from '@studio/routes/ExperimentRoute/ExperimentCard';
import { keepPreviousData } from '@tanstack/react-query';
import { CircleAlert } from 'lucide-react';
import { type ComponentProps, type FC, useMemo, useState } from 'react';

const DEFAULT_PAGE_SIZE = 10;

/**
 * Column filters available for experiment groups. `created_at` / `updated_at` are base entity
 * fields the list endpoint filters via `$gte` / `$lte` ranges. They are not declared on the
 * generated `ExperimentFilter` type, so the API filter is widened here and coerced back at
 * the SDK boundary (see `filter` below).
 */
interface ExperimentColumnFilters {
  created_at?: DatetimeFilterValue;
  updated_at?: DatetimeFilterValue;
}

type ExperimentFilterInput = WithFilterOperators<ExperimentFilter> &
  ExperimentColumnFilters;

/**
 * Filter-only columns. They are never rendered as a table (the cards come from CustomContent);
 * they exist solely to feed `meta.filter` into the DataView filter panel and applied-filter tags.
 */
const makeFilterColumns: ComponentProps<
  typeof DataView.Root<ExperimentResponse>
>['makeColumns'] = ({ accessor }) => [
  accessor('created_at', {
    id: 'created_at',
    header: 'Created',
    enableSorting: false,
    meta: { filter: dateTimeFilter('Created At') },
  }),
  accessor('updated_at', {
    id: 'updated_at',
    header: 'Updated',
    enableSorting: false,
    meta: { filter: dateTimeFilter('Updated At') },
  }),
];

export const ExperimentRoute: FC = () => {
  useBreadcrumbs({ items: [{ slotLabel: 'Experiments' }] });

  const workspace = useWorkspaceFromPath();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const dataViewState = useStudioDataViewState<ExperimentColumnFilters>({
    defaultPageSize: DEFAULT_PAGE_SIZE,
  });
  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;
  const searchText = dataViewState.apiFilter.searchText;
  const columnFilters = dataViewState.apiFilter.filter;

  const filter = useMemo<ExperimentFilter | undefined>(() => {
    if (!searchText && !columnFilters) return undefined;
    const input: ExperimentFilterInput = {
      ...columnFilters,
      ...(searchText ? { name: { $like: searchText } } : {}),
    };
    return input as ExperimentFilter;
  }, [columnFilters, searchText]);

  const { data, isLoading, error } = useListExperiments(
    workspace,
    { page, page_size: pageSize, filter },
    { query: { placeholderData: keepPreviousData } }
  );

  const groups = data?.data ?? [];
  const totalResults = data?.pagination?.total_results ?? 0;

  return (
    <AccessibleTitle title="Experiment groups">
      <Stack className="h-full min-h-0" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0 shrink-0"
          slotHeading={
            <>
              Experiment groups
              <FeatureFlagBadge flag="experiment" />
            </>
          }
          slotDescription="Manage groups for online optimization. Review reports down to the frame level."
          slotActions={
            <Button color="brand" onClick={() => setIsCreateModalOpen(true)}>
              New experiment group
            </Button>
          }
        />
        <ExperimentCreateModal
          open={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          workspace={workspace}
        />
        <StudioDataView<ExperimentResponse>
          dataViewState={dataViewState}
          makeColumns={makeFilterColumns}
          searchField="name"
          attributes={{
            DataViewRoot: {
              data: groups,
              totalCount: totalResults,
              requestStatus: error ? 'error' : isLoading ? 'loading' : undefined,
            },
            DataViewSearchBar: { placeholder: 'Search experiment groups...' },
          }}
        >
          <Stack className="h-full min-h-0" gap="density-md">
            <Block className="flex-1 min-h-0 overflow-auto">
              <DataView.CustomContent<ExperimentResponse>
                renderLoadingState={() => <Loading description="Loading experiments..." />}
                renderEmptyState={({ hasSearchApplied, hasFiltersApplied }) => (
                  <Flex justify="center" className="p-density-2xl">
                    <Text kind="body/regular/md" className="text-secondary">
                      {hasSearchApplied || hasFiltersApplied
                        ? 'No experiment groups match your search or filters.'
                        : 'No experiment groups yet.'}
                    </Text>
                  </Flex>
                )}
                renderErrorState={() => (
                  <Flex justify="center" className="p-density-2xl">
                    <StatusMessage
                      size="medium"
                      slotMedia={<CircleAlert width={65} height={65} />}
                      slotHeading="Error loading experiments"
                      slotSubheading={error?.message}
                    />
                  </Flex>
                )}
              >
                {({ rows }) => (
                  <Stack gap="density-md">
                    {rows.map((row) => (
                      <ExperimentCard
                        key={row.original.id}
                        group={row.original}
                        workspace={workspace}
                      />
                    ))}
                  </Stack>
                )}
              </DataView.CustomContent>
            </Block>
            <DataView.Pagination
              className="px-density-2xl py-density-lg"
              showItemsPerPage
              showWhileLessThanPageSize
              pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            >
              <>
                <PaginationControlsGroup>
                  <Text className="@max-2xl:hidden">Items per page</Text>
                  <PaginationPageSizeSelect />
                  <PaginationDivider className="@max-lg:hidden" />
                  <PaginationItemRangeText className="@max-lg:hidden" />
                </PaginationControlsGroup>
                <PaginationNavigationGroup className="gap-2">
                  <PaginationArrowButton direction="first" />
                  <PaginationArrowButton direction="previous" />
                  <PaginationPageInput />
                  <PaginationPageCountText
                    pageCountTextFormatFn={(pageMeta) => `of ${pageMeta.total}`}
                  />
                  <PaginationArrowButton direction="next" />
                  <PaginationArrowButton direction="last" />
                </PaginationNavigationGroup>
              </>
            </DataView.Pagination>
          </Stack>
        </StudioDataView>
      </Stack>
    </AccessibleTitle>
  );
};
