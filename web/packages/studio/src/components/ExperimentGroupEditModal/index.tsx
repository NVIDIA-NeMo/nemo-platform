// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getGetExperimentGroupQueryKey,
  getListExperimentGroupsQueryKey,
  useListExperiments,
  useUpdateExperimentGroup,
} from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import { FormField, Stack, TextArea, TextInput } from '@nvidia/foundations-react-core';
import { queryClient } from '@studio/api/queryClient';
import { DefaultSortControl } from '@studio/components/DefaultSortControl';
import { AxiosError } from 'axios';
import { type FC, type FormEvent, useEffect, useMemo, useState } from 'react';

export interface ExperimentGroupEditModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  group: ExperimentGroupResponse;
}

export const ExperimentGroupEditModal: FC<ExperimentGroupEditModalProps> = ({
  open,
  onClose,
  workspace,
  group,
}) => {
  const toast = useToast();
  const [description, setDescription] = useState(group.description ?? '');
  const [defaultSort, setDefaultSort] = useState<string>(group.default_sort);

  // Reset local form state whenever the modal (re)opens or points at a different group.
  useEffect(() => {
    if (open) {
      setDescription(group.description ?? '');
      setDefaultSort(group.default_sort);
    }
  }, [open, group]);

  // Offer the group's discovered evaluators as first-class sort fields (only fetched while open).
  const { data: experimentsPage } = useListExperiments(
    workspace,
    { filter: { experiment_group_id: group.id }, page_size: 100 },
    { query: { enabled: open && !!group.id } }
  );
  const evaluatorOptions = useMemo(
    () =>
      [
        ...new Set(
          (experimentsPage?.data ?? []).flatMap((e) => Object.keys(e.aggregate_scores ?? {}))
        ),
      ].sort(),
    [experimentsPage]
  );

  const { mutateAsync: updateExperimentGroup, isPending } = useUpdateExperimentGroup({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetExperimentGroupQueryKey(workspace, group.name),
        });
        queryClient.invalidateQueries({ queryKey: getListExperimentGroupsQueryKey(workspace) });
      },
    },
  });

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); // FormModal doesn't preventDefault; without RHF's handler we must.
    try {
      await updateExperimentGroup({
        workspace,
        name: group.name,
        data: {
          // Name is immutable for a group; send it unchanged so the update isn't treated as a rename.
          name: group.name,
          description: description || undefined,
          default_sort: defaultSort,
        },
      });
      onClose();
    } catch (error) {
      const detail = error instanceof AxiosError ? error.response?.data?.detail : undefined;
      const message =
        typeof detail === 'string'
          ? detail
          : error instanceof Error
            ? error.message
            : 'Unknown error';
      toast.error(`Failed to update experiment group: ${message}`);
    }
  };

  return (
    <FormModal
      title="Edit experiment group"
      instruction="Update the group's description and default sort order."
      submitButtonText={isPending ? 'Saving…' : 'Save'}
      disabled={isPending}
      loading={isPending}
      onSubmit={onSubmit}
      onClose={onClose}
      open={open}
      className="w-[800px] min-h-[400px]"
    >
      <Stack gap="density-2xl" className="w-full">
        <FormField slotLabel="Name">
          <TextInput value={group.name} disabled />
        </FormField>
        <FormField slotLabel="Description (optional)">
          <TextArea
            disabled={isPending}
            value={description}
            onValueChange={(v: string) => setDescription(v)}
          />
        </FormField>
        <DefaultSortControl
          value={defaultSort}
          onChange={setDefaultSort}
          evaluatorOptions={evaluatorOptions}
          disabled={isPending}
        />
      </Stack>
    </FormModal>
  );
};
