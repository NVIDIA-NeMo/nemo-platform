// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getListEvaluationsQueryKey,
  useAddEvaluationToGroup,
  useListExperimentGroups,
} from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  Flex,
  ModalContent,
  ModalDialog,
  ModalFooter,
  ModalHeading,
  ModalMain,
  ModalRoot,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useMemo, useState } from 'react';

export interface AddToGroupModalProps {
  open: boolean;
  onClose: () => void;
  workspace: string;
  /** The evaluation being curated into another group. */
  evaluation: EvaluationRow;
  /**
   * The group whose board is currently shown. Its evaluation list is invalidated on success so the
   * board refreshes — mirroring how the pin action scopes invalidation to the current group.
   */
  currentExperimentGroupId: string;
}

/**
 * Adds an evaluation to another ExperimentGroup. Shows a searchable list of the workspace's groups —
 * excluding the ones the evaluation already belongs to — and adds the evaluation to whichever group
 * the user selects, then refreshes the current board and toasts the result.
 */
export const AddToGroupModal: FC<AddToGroupModalProps> = ({
  open,
  onClose,
  workspace,
  evaluation,
  currentExperimentGroupId,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');

  // Clear the filter whenever the modal (re)opens so a stale search doesn't hide groups.
  useEffect(() => {
    if (open) setSearch('');
  }, [open]);

  // Only fetch groups while the modal is open. A single large page covers any realistic group count.
  const { data: groupsPage, isLoading } = useListExperimentGroups(
    workspace,
    { page_size: 1000 },
    { query: { enabled: open && !!workspace } }
  );

  // The evaluation already belongs to these groups, so they're not valid add targets.
  const memberIds = useMemo(() => new Set(evaluation.experiment_ids), [evaluation.experiment_ids]);

  // Exclude current members, then filter by the (case-insensitive) search text on the group name.
  const groups = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (groupsPage?.data ?? [])
      .filter((group) => !memberIds.has(group.id))
      .filter((group) => !query || group.name.toLowerCase().includes(query));
  }, [groupsPage, memberIds, search]);

  const { mutate: addEvaluationToGroup, isPending } = useAddEvaluationToGroup();

  const handleSelect = (group: ExperimentGroupResponse) => {
    if (isPending) return;
    addEvaluationToGroup(
      { workspace, name: evaluation.name, groupId: group.id },
      {
        // Mirror the pin action's invalidation: scope to the current group's evaluation lists (any
        // page/sort/filter) via a partial key match so the board refreshes without touching other
        // groups' queries.
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getListEvaluationsQueryKey(workspace, {
              filter: { experiment_group_id: currentExperimentGroupId },
            }),
          });
          toast.success(`Added "${evaluation.name}" to "${group.name}".`);
          onClose();
        },
        onError: () => toast.error(`Failed to add "${evaluation.name}" to "${group.name}".`),
      }
    );
  };

  return (
    <ModalRoot open={open} onOpenChange={onClose}>
      <ModalDialog>
        <ModalContent className="max-h-[90vh] w-[560px]">
          <ModalHeading>Add to group</ModalHeading>
          <ModalMain className="flex-1 min-h-0 overflow-y-auto">
            <Stack gap="density-md" className="pt-4 w-full">
              <Text kind="body/regular/sm" className="text-secondary whitespace-normal">
                Add "{evaluation.name}" to another experiment group to compare it across boards.
              </Text>
              <TextInput
                value={search}
                onValueChange={setSearch}
                placeholder="Search groups by name"
                aria-label="Search groups"
                disabled={isPending}
              />
              <Stack
                gap="density-xxs"
                className="w-full"
                role="listbox"
                aria-label="Experiment groups"
              >
                {isLoading ? (
                  <Text kind="body/regular/sm" className="text-secondary">
                    Loading groups…
                  </Text>
                ) : groups.length === 0 ? (
                  <Text kind="body/regular/sm" className="text-secondary">
                    No groups found.
                  </Text>
                ) : (
                  groups.map((group) => (
                    <Button
                      key={group.id}
                      kind="tertiary"
                      color="neutral"
                      role="option"
                      className="w-full justify-start"
                      disabled={isPending}
                      onClick={() => handleSelect(group)}
                    >
                      <Text>{group.name}</Text>
                    </Button>
                  ))
                )}
              </Stack>
            </Stack>
          </ModalMain>
          <ModalFooter className="flex w-full gap-2 flex-shrink-0 justify-end">
            <Flex gap="2">
              <Button kind="tertiary" type="button" onClick={onClose} disabled={isPending}>
                Cancel
              </Button>
            </Flex>
          </ModalFooter>
        </ModalContent>
      </ModalDialog>
    </ModalRoot>
  );
};
