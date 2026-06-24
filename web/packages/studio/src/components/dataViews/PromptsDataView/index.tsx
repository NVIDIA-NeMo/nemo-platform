// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { useModelsDeletePrompt, useModelsListPrompts } from '@nemo/sdk/generated/platform/api';
import type { Prompt } from '@nemo/sdk/generated/platform/schema';
import { Button, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { PromptIconFc } from '@studio/constants/constants';
import { keepPreviousData } from '@tanstack/react-query';
import { Trash } from 'lucide-react';
import { ComponentProps, FC, useCallback, useMemo, useState } from 'react';

export interface PromptsDataViewProps {
  workspace: string;
  emptyStateActions?: React.ReactNode;
  attributes?: {
    Stack?: React.ComponentProps<typeof Stack>;
  };
}

type PromptWithId = Prompt & { id: string };

export const PromptsDataView: FC<PromptsDataViewProps> = ({
  workspace,
  emptyStateActions,
  attributes,
}) => {
  const toast = useToast();

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
  });

  const [promptToDelete, setPromptToDelete] = useState<Prompt>();

  const { data, refetch, isFetching, error } = useModelsListPrompts(
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

  const deletePromptMutation = useModelsDeletePrompt();

  const prompts = useMemo(() => data?.data ?? [], [data?.data]);
  const pagination = data?.pagination;

  const searchBar = dataViewState.searchBar.state;
  const filteredPrompts = useMemo(() => {
    if (!searchBar) return prompts;
    return prompts.filter((prompt: Prompt) =>
      prompt.name?.toLowerCase().includes(searchBar.toLowerCase())
    );
  }, [prompts, searchBar]);

  const promptsWithId = useMemo<PromptWithId[]>(
    () =>
      filteredPrompts.map((prompt: Prompt) => ({
        ...prompt,
        id: `${prompt.workspace}/${prompt.name}`,
      })),
    [filteredPrompts]
  );

  const handleDeletePrompt = async () => {
    if (!promptToDelete) return false;

    try {
      await deletePromptMutation.mutateAsync({
        workspace,
        name: promptToDelete.name,
      });
      refetch();
      return true;
    } catch {
      toast.error('Failed to delete prompt');
      return false;
    }
  };

  const makeColumns: ComponentProps<typeof StudioDataView<PromptWithId>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowActionsColumn }) => [
        accessor('name', {
          header: 'Name',
          enableSorting: false,
          size: 200,
        }),
        accessor('description', {
          header: 'Description',
          cell({ row }) {
            return (
              <Text className="truncate" title={row.original.description}>
                {row.original.description || '-'}
              </Text>
            );
          },
        }),
        accessor('tags', {
          header: 'Tags',
          enableSorting: false,
          size: 180,
          cell({ row }) {
            const tags = row.original.tags;
            if (!tags?.length) return <Text>-</Text>;
            return (
              <Text className="truncate" title={tags.join(', ')}>
                {tags.join(', ')}
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
        accessor('updated_at', {
          header: 'Updated',
          enableSorting: true,
          size: 150,
          cell({ row }) {
            return row.original.updated_at ? (
              <RelativeTime datetime={row.original.updated_at} />
            ) : (
              <Text>-</Text>
            );
          },
        }),
        rowActionsColumn({
          size: ROW_ACTIONS_COLUMN_SIZE,
          enableResizing: false,
          rowActions: (prompt: PromptWithId) => [
            {
              slotLeft: <Trash />,
              children: 'Delete',
              danger: true,
              onSelect: () => setPromptToDelete(prompt),
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
            placeholder: 'Search Prompts...',
          },
          DataViewRoot: {
            data: promptsWithId,
            totalCount: pagination?.total_results,
            requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () =>
              hasActiveFilters ? (
                <TableEmptyState
                  header="No Results Found"
                  emptyMessage="No prompts match your search"
                  actions={
                    <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                      Clear Search
                    </Button>
                  }
                />
              ) : (
                <TableEmptyState
                  icon={<PromptIconFc className="size-16" />}
                  header="No Prompts Yet"
                  emptyMessage="Reusable prompt templates will appear here once created."
                  actions={emptyStateActions}
                />
              ),
            renderErrorState: () => (
              <ErrorPanel
                errorMessage={getErrorMessage(error ?? new Error('Failed to fetch prompts'))}
              />
            ),
          },
        }}
      />

      {promptToDelete && (
        <DeleteConfirmationModal
          open
          simpleConfirm
          onDelete={handleDeletePrompt}
          title={`Delete: ${promptToDelete.name}`}
          description="Are you sure you want to delete this prompt?"
          onClose={() => setPromptToDelete(undefined)}
        />
      )}
    </Stack>
  );
};
