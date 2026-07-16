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

import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { useSecretsDeleteSecret, useSecretsListSecrets } from '@nemo/sdk/generated/platform/api';
import { PlatformSecretResponse } from '@nemo/sdk/generated/platform/schema';
import { Button, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { LINK_DOCS_SECRETS } from '@studio/constants/links';
import { EditSecretModal } from '@studio/routes/SecretsListRoute/EditSecretModal';
import { keepPreviousData } from '@tanstack/react-query';
import { LockKeyhole, Pencil, Trash } from 'lucide-react';
import { ComponentProps, FC, useCallback, useMemo, useState } from 'react';

export interface SecretsDataViewProps {
  workspace: string;
  emptyStateActions?: React.ReactNode;
  attributes?: {
    Stack?: React.ComponentProps<typeof Stack>;
  };
}

type SecretWithId = PlatformSecretResponse & { id: string };

type ModalState = 'delete' | 'edit' | 'none';

export const SecretsDataView: FC<SecretsDataViewProps> = ({
  workspace,
  emptyStateActions,
  attributes,
}) => {
  const toast = useToast();

  const dataViewState = useStudioDataViewState({
    defaultSort: [{ id: 'created_at', desc: true }],
  });

  const [modalSecret, setModalSecret] = useState<PlatformSecretResponse>();
  const [modalOpen, setModalOpen] = useState<ModalState>('none');

  const { data, refetch, isFetching, error } = useSecretsListSecrets(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
    },
    {
      query: {
        placeholderData: keepPreviousData,
      },
    }
  );

  const deleteSecretMutation = useSecretsDeleteSecret();

  const secrets = useMemo(() => data?.data || [], [data?.data]);
  const pagination = data?.pagination;

  // Filter secrets by search text (API does not support server-side search)
  const searchBar = dataViewState.searchBar.state;
  const filteredSecrets = useMemo(() => {
    if (!searchBar) return secrets;
    return secrets.filter((secret: PlatformSecretResponse) =>
      secret.name?.toLowerCase().includes(searchBar.toLowerCase())
    );
  }, [secrets, searchBar]);

  // Add id to each secret for DataView
  const secretsWithId = useMemo<SecretWithId[]>(
    () =>
      filteredSecrets.map((secret: PlatformSecretResponse) => ({
        ...secret,
        id: `${secret.workspace}/${secret.name}`,
      })),
    [filteredSecrets]
  );

  const handleDeleteSecret = async () => {
    if (!modalSecret) return false;

    try {
      await deleteSecretMutation.mutateAsync({
        workspace,
        name: modalSecret.name!,
      });
      refetch();
      return true;
    } catch {
      toast.error('Failed to delete secret');
      return false;
    }
  };

  const handleModalClose = () => {
    setModalOpen('none');
    setModalSecret(undefined);
  };

  // Column definitions
  const makeColumns: ComponentProps<typeof StudioDataView<SecretWithId>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowActionsColumn }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: false,
          size: 175,
        }),
        accessor('description', {
          header: 'Description',
          cell({ row }) {
            const secret = row.original;
            return (
              <Text className="truncate" title={secret.description}>
                {secret.description || '-'}
              </Text>
            );
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
          size: ROW_ACTIONS_COLUMN_SIZE,
          enableResizing: false,
          rowActions: (secret: SecretWithId) => [
            {
              slotLeft: <Pencil />,
              children: 'Edit',
              onSelect: () => {
                setModalSecret(secret);
                setModalOpen('edit');
              },
            },
            {
              slotLeft: <Trash />,
              children: 'Delete',
              danger: true,
              onSelect: () => {
                setModalSecret(secret);
                setModalOpen('delete');
              },
            },
          ],
        }),
      ],
      []
    );

  const hasActiveFilters = !!searchBar;

  return (
    <Stack gap="density-2xl" {...attributes?.Stack}>
      <StudioDataView
        dataViewState={dataViewState}
        searchField="name"
        makeColumns={makeColumns}
        attributes={{
          DataViewSearchBar: {
            placeholder: 'Search Secrets...',
          },
          DataViewRoot: {
            data: secretsWithId,
            totalCount: pagination?.total_results,
            requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No secrets match your search"
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Search
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  icon={<LockKeyhole className="size-16" />}
                  header="Manage Secrets"
                  emptyMessage="Start by creating a secret, refer to the documentation for formatting details."
                  actions={
                    <Stack direction="row" gap="density-md">
                      <DocumentationButton href={LINK_DOCS_SECRETS} />
                      {emptyStateActions}
                    </Stack>
                  }
                />
              ),
            renderErrorState: () => (
              <ErrorPanel
                errorMessage={getErrorMessage(error ?? new Error('Failed to fetch secrets'))}
              />
            ),
          },
        }}
      />

      {modalOpen === 'delete' && modalSecret && (
        <DeleteConfirmationModal
          open
          simpleConfirm
          onDelete={handleDeleteSecret}
          title={`Delete: ${modalSecret.name}`}
          description="Are you sure you want to delete?"
          onClose={handleModalClose}
        />
      )}

      {modalOpen === 'edit' && modalSecret && (
        <EditSecretModal
          workspace={workspace}
          secret={modalSecret}
          open
          onClose={handleModalClose}
        />
      )}
    </Stack>
  );
};
