/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useModelsListDeployments } from '@nemo/sdk/generated/platform/api';
import {
  ModelDeployment,
  ModelDeploymentFilter,
  ModelDeploymentStatus,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { CUSTOMIZER_ENABLED } from '@studio/constants/environment';
import { keepPreviousData } from '@tanstack/react-query';
import { Rocket, Trash2 } from 'lucide-react';
import { ComponentProps, FC, useCallback } from 'react';

export interface DeploymentsDataViewProps {
  workspace: string;
  emptyStateActions?: React.ReactNode;
  /** Opens the URL-driven deployment details panel (row click). */
  onDeploymentRowClick: (deployment: ModelDeployment) => void;
  /** Opens the shared delete confirmation flow (row action menu). */
  onRequestDeleteDeployment: (deployment: ModelDeployment) => void;
  attributes?: {
    Stack?: React.ComponentProps<typeof Stack>;
  };
}

export const DeploymentsDataView: FC<DeploymentsDataViewProps> = ({
  workspace,
  emptyStateActions,
  onDeploymentRowClick,
  onRequestDeleteDeployment,
  attributes,
}) => {
  const dataViewState = useStudioDataViewState({
    defaultSort: [{ id: 'created_at', desc: true }],
  });

  const resetFilters = useCallback(() => {
    dataViewState.resetFilters();
  }, [dataViewState]);

  const sortState = dataViewState.sorting.state[0];
  const sortParam = sortState ? `${sortState.desc ? '-' : ''}${sortState.id}` : '-created_at';

  const { data, isFetching, error } = useModelsListDeployments(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: sortParam,
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.apiFilter.searchText
          ? withOperators<ModelDeploymentFilter>({
              name: { $like: dataViewState.apiFilter.searchText },
            })
          : {}),
      },
    },
    {
      query: {
        placeholderData: keepPreviousData,
      },
    }
  );

  const pagination = data?.pagination;

  const makeColumns: ComponentProps<typeof StudioDataView<ModelDeployment>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowActionsColumn }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: false,
          size: 175,
          cell({ row }) {
            return <Text className="font-bold">{row.original.name}</Text>;
          },
        }),
        accessor('status', {
          header: 'Status',
          size: 120,
          cell({ row }) {
            return <StatusBadge status={row.original.status} />;
          },
        }),
        accessor('created_at', {
          header: 'Created',
          enableSorting: true,
          size: 150,
          cell({ row }) {
            return row.original.created_at ? (
              <RelativeTime datetime={row.original.created_at} />
            ) : (
              <Text>-</Text>
            );
          },
        }),
        rowActionsColumn({
          size: 58,
          enableResizing: false,
          rowActions: (deployment: ModelDeployment) => [
            {
              slotLeft: <Trash2 />,
              children: 'Delete',
              disabled:
                deployment.status === ModelDeploymentStatus.DELETED ||
                deployment.status === ModelDeploymentStatus.DELETING,
              danger: true,
              onSelect: () => onRequestDeleteDeployment(deployment),
            },
          ],
        }),
      ],
      [onRequestDeleteDeployment]
    );

  const hasSearchOrFilters = !!dataViewState.debouncedSearchBar;

  return (
    <Stack gap="density-2xl" {...attributes?.Stack}>
      <StudioDataView
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={onDeploymentRowClick}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search Deployments...',
          },
          DataViewRoot: {
            data: data?.data ?? [],
            totalCount: pagination?.total_results,
            requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () => {
              if (data?.data.length === 0 && !isFetching && !hasSearchOrFilters) {
                return (
                  <TableEmptyState
                    icon={<Rocket className="h-[64px] w-[64px]" />}
                    header="Manage Deployments"
                    emptyMessage={
                      CUSTOMIZER_ENABLED
                        ? 'Deploy an open source model from the base models or create a fine-tuned model.'
                        : 'Deploy an open source model from the base models.'
                    }
                    actions={<Flex gap="2">{emptyStateActions}</Flex>}
                  />
                );
              }
              return (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No deployments match your search"
                  actions={
                    <Button kind="tertiary" onClick={resetFilters}>
                      Clear Search
                    </Button>
                  }
                />
              );
            },
            renderErrorState: () => (
              <ErrorPanel
                errorMessage={getErrorMessage(error ?? new Error('Failed to fetch deployments'))}
              />
            ),
          },
        }}
      />
    </Stack>
  );
};
