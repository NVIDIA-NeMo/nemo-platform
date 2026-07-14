// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useDeferredUnmount } from '@nemo/common/src/hooks/useDeferredUnmount';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getListVirtualModelsQueryKey,
  useDeleteVirtualModel,
  useListVirtualModels,
} from '@nemo/sdk/generated/platform/api';
import type {
  DatetimeFilter,
  VirtualModel,
  VirtualModelFilter,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { VirtualModelDetailsSidePanel } from '@studio/routes/VirtualModelsListRoute/VirtualModelDetailsSidePanel';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { Waypoints } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo, useState } from 'react';

export interface VirtualModelsDataViewProps {
  workspace: string;
  attributes?: {
    Stack?: React.ComponentProps<typeof Stack>;
  };
}

type VirtualModelWithId = VirtualModel & { id: string };

const middlewareCount = (vm: VirtualModel): number =>
  (vm.request_middleware?.length ?? 0) +
  (vm.response_middleware?.length ?? 0) +
  (vm.post_response_middleware?.length ?? 0);

export const VirtualModelsDataView: FC<VirtualModelsDataViewProps> = ({
  workspace,
  attributes,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  const {
    isOpen: isDetailsPanelOpen,
    value: vmForDetails,
    open: openDetailsPanel,
    close: closeDetailsPanel,
  } = useDeferredUnmount<VirtualModelWithId>({ delay: 300 });

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const [modalVirtualModel, setModalVirtualModel] = useState<VirtualModel>();

  const sortState = dataViewState.sorting.state[0];
  const sortParam = sortState
    ? sortState.desc
      ? `-${sortState.id}`
      : sortState.id
    : '-created_at';

  const filter = useMemo<VirtualModelFilter>(() => {
    const columnFilters = new Map(dataViewState.debouncedColumnFilters.map((f) => [f.id, f.value]));
    const name = dataViewState.debouncedSearchBar || undefined;
    const defaultModelEntity = columnFilters.get('default_model_entity') as string | undefined;
    const createdAt = columnFilters.get('created_at') as DatetimeFilter | undefined;
    return withOperators<VirtualModelFilter>({
      ...(name ? { name: { $like: name } } : {}),
      ...(defaultModelEntity ? { default_model_entity: { $like: defaultModelEntity } } : {}),
      ...(createdAt ? { created_at: createdAt } : {}),
    });
  }, [dataViewState.debouncedSearchBar, dataViewState.debouncedColumnFilters]);

  const { data, isFetching, error } = useListVirtualModels(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: sortParam,
      filter,
      // Autoprovisioned VMs are controller-managed passthroughs; hide them from the UI.
      exclude_autoprovisioned: true,
    },
    {
      query: {
        placeholderData: keepPreviousData,
      },
    }
  );

  const deleteVirtualModelMutation = useDeleteVirtualModel({
    mutation: {
      onSuccess: () => {
        toast.success('Virtual model deleted successfully.');
        queryClient.invalidateQueries({
          queryKey: getListVirtualModelsQueryKey(workspace),
        });
      },
    },
  });

  const virtualModels = useMemo(() => data?.data ?? [], [data?.data]);
  const pagination = data?.pagination;

  const virtualModelsWithId = useMemo<VirtualModelWithId[]>(
    () =>
      virtualModels.map((vm: VirtualModel) => ({
        ...vm,
        id: `${vm.workspace}/${vm.name}`,
      })),
    [virtualModels]
  );

  const handleDeleteVirtualModel = async () => {
    if (!modalVirtualModel?.name) return false;
    try {
      await deleteVirtualModelMutation.mutateAsync({
        workspace,
        name: modalVirtualModel.name,
      });
      return true;
    } catch {
      toast.error('Failed to delete virtual model');
      return false;
    }
  };

  const handleModalClose = () => {
    setModalVirtualModel(undefined);
  };

  const makeColumns: ComponentProps<typeof StudioDataView<VirtualModelWithId>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowActionsColumn }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: true,
          size: 200,
          cell({ row }) {
            return <Text>{row.original.name}</Text>;
          },
        }),
        accessor('default_model_entity', {
          header: 'Default model',
          enableSorting: false,
          meta: {
            filter: { type: 'text', label: 'Default Model' },
          },
          cell({ row }) {
            const value = row.original.default_model_entity;
            return (
              <Text className="truncate max-w-[280px]" title={value}>
                {value || '—'}
              </Text>
            );
          },
        }),
        accessor((vm) => middlewareCount(vm), {
          id: 'middleware',
          header: 'Middleware',
          enableSorting: false,
          size: 120,
          cell({ row }) {
            const count = middlewareCount(row.original);
            return <Text>{count === 0 ? 'None' : `${count} call${count === 1 ? '' : 's'}`}</Text>;
          },
        }),
        accessor('created_at', {
          header: 'Created',
          enableSorting: true,
          size: 150,
          meta: {
            filter: dateTimeFilter('Created At'),
          },
          cell({ row }) {
            return row.original.created_at ? (
              <RelativeTime datetime={row.original.created_at} />
            ) : (
              <Text>—</Text>
            );
          },
        }),
        rowActionsColumn({
          size: ROW_ACTIONS_COLUMN_SIZE,
          enableResizing: false,
          cellProps: {
            attributes: {
              DropdownContent: { className: 'min-w-[156px]' },
            },
          },
          rowActions: (vm: VirtualModelWithId) => [
            {
              children: 'View',
              onSelect: () => openDetailsPanel(vm),
            },
            {
              children: 'Delete',
              danger: true,
              onSelect: () => setModalVirtualModel(vm),
            },
          ],
        }),
      ],
      [openDetailsPanel]
    );

  const hasSearchOrFilters =
    !!dataViewState.debouncedSearchBar || dataViewState.debouncedColumnFilters.length > 0;
  const isInitialEmpty =
    virtualModelsWithId.length === 0 && !isFetching && !error && !hasSearchOrFilters;

  const emptyState = (
    <Flex
      justify="center"
      align="center"
      className="h-full min-h-[min(480px,60vh)] w-full py-density-3xl"
    >
      <StatusMessage
        className="max-w-lg"
        size="medium"
        slotHeading="No Virtual Models"
        slotSubheading="Auto-provisioned passthrough routes are hidden. Create virtual models via the CLI or SDK to define custom inference routing and middleware pipelines."
        slotMedia={<Waypoints className="w-[48px] h-[48px]" />}
      />
    </Flex>
  );

  return (
    <Stack gap="density-xl" {...attributes?.Stack}>
      <StudioDataView
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        onRowClick={(row: VirtualModelWithId) => openDetailsPanel(row)}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search by name...',
          },
          DataViewRoot: {
            data: virtualModelsWithId,
            totalCount: pagination?.total_results,
            requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              isInitialEmpty ? (
                emptyState
              ) : (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No virtual models match your search or filters"
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Filters
                    </Button>
                  }
                />
              ),
            renderErrorState: () => (
              <ErrorPanel
                errorMessage={getErrorMessage(error ?? new Error('Failed to fetch virtual models'))}
              />
            ),
          },
        }}
      />

      {modalVirtualModel && (
        <DeleteConfirmationModal
          open
          simpleConfirm
          onDelete={handleDeleteVirtualModel}
          title={`Delete virtual model: ${modalVirtualModel.name}`}
          confirmationText={modalVirtualModel.name}
          onClose={handleModalClose}
          description="Deleting this virtual model removes its inference route and middleware pipelines. Are you sure you want to proceed?"
        />
      )}

      {vmForDetails != null && (
        <VirtualModelDetailsSidePanel
          open={isDetailsPanelOpen}
          virtualModel={vmForDetails}
          onClose={closeDetailsPanel}
        />
      )}
    </Stack>
  );
};
