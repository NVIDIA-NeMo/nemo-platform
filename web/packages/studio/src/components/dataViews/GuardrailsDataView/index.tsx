// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useGuardrailsListGuardrailConfigs } from '@nemo/sdk/generated/platform/api';
import type {
  GuardrailConfig,
  GuardrailsListGuardrailConfigsParams,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { countRails } from '@studio/components/dataViews/GuardrailsDataView/guardrailUtils';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { keepPreviousData } from '@tanstack/react-query';
import { ShieldCheck, Trash } from 'lucide-react';
import { type ComponentProps, type FC, useCallback } from 'react';

export interface GuardrailsDataViewProps {
  workspace: string;
  onRowClick: (config: GuardrailConfig) => void;
  onRequestDelete?: (config: GuardrailConfig) => void;
  emptyStateActions?: React.ReactNode;
}

export const GuardrailsDataView: FC<GuardrailsDataViewProps> = ({
  workspace,
  onRowClick,
  onRequestDelete,
  emptyStateActions,
}) => {
  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const sortState = dataViewState.sorting.state[0];
  const sortParam = (
    sortState ? `${sortState.desc ? '-' : ''}${sortState.id}` : 'created_at'
  ) as GuardrailsListGuardrailConfigsParams['sort'];

  const { data, isFetching, error } = useGuardrailsListGuardrailConfigs(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: sortParam,
    },
    {
      query: { placeholderData: keepPreviousData },
    }
  );

  const pagination = data?.pagination;
  const hasSearchOrFilters = !!dataViewState.debouncedSearchBar;

  const makeColumns: ComponentProps<typeof StudioDataView<GuardrailConfig>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowActionsColumn }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: true,
          size: 180,
          cell({ row }) {
            return <Text className="font-bold">{row.original.name}</Text>;
          },
        }),
        accessor('description', {
          header: 'Description',
          enableSorting: false,
          cell({ row }) {
            return (
              <Text className="truncate" title={row.original.description ?? ''}>
                {row.original.description ?? '—'}
              </Text>
            );
          },
        }),
        accessor('data', {
          id: 'models',
          header: 'Models',
          enableSorting: false,
          size: 80,
          cell({ row }) {
            return <Text>{row.original.data?.models?.length ?? 0}</Text>;
          },
        }),
        accessor('data', {
          id: 'rails',
          header: 'Rails',
          enableSorting: false,
          size: 80,
          cell({ row }) {
            return <Text>{countRails(row.original.data)}</Text>;
          },
        }),
        accessor('updated_at', {
          header: 'Updated',
          enableSorting: false,
          size: 140,
          cell({ row }) {
            return row.original.updated_at ? (
              <RelativeTime datetime={row.original.updated_at} />
            ) : (
              <Text>—</Text>
            );
          },
        }),
        rowActionsColumn({
          size: ROW_ACTIONS_COLUMN_SIZE,
          enableResizing: false,
          rowActions: (config: GuardrailConfig) => [
            {
              slotLeft: <Trash />,
              children: 'Delete',
              danger: true,
              onSelect: () => onRequestDelete?.(config),
            },
          ],
        }),
      ],
      [onRequestDelete]
    );

  return (
    <StudioDataView
      dataViewState={dataViewState}
      searchField="name"
      makeColumns={makeColumns}
      onRowClick={(row: GuardrailConfig) => onRowClick(row)}
      attributes={{
        DataViewSearchBar: { placeholder: 'Search Guardrail Configs...' },
        DataViewRoot: {
          data: data?.data ?? [],
          totalCount: pagination?.total_results,
          requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () => {
            if (data?.data?.length === 0 && !isFetching && !hasSearchOrFilters) {
              return (
                <TableEmptyState
                  icon={<ShieldCheck className="h-[64px] w-[64px]" />}
                  header="Manage Guardrail Configs"
                  emptyMessage="Create a guardrail configuration to protect your workspace models."
                  actions={<Flex gap="2">{emptyStateActions}</Flex>}
                />
              );
            }
            return (
              <TableEmptyState
                header="No Results Found"
                emptyMessage="No guardrail configs match your search"
                actions={
                  <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                    Clear Search
                  </Button>
                }
              />
            );
          },
          renderErrorState: () => (
            <ErrorPanel
              errorMessage={getErrorMessage(
                error ?? new Error('Failed to fetch guardrail configs')
              )}
            />
          ),
        },
      }}
    />
  );
};
