// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CJobCancellableStatuses } from '@nemo/common/src/constants/query';
import {
  getAnonymizerListRunJobsQueryKey,
  useAnonymizerCancelRunJob,
} from '@nemo/sdk/generated/anonymizer/api';
import type { RunJob as AnonymizerJob } from '@nemo/sdk/generated/anonymizer/schema';
import { DeleteJobModal } from '@studio/components/dataViews/AnonymizerJobsDataView/DeleteJobModal';
import {
  type QuickActionItem,
  QuickActionsMenuRoot,
} from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getAnonymizerJobRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface AnonymizerJobActionsMenuProps {
  job: AnonymizerJob;
  includeViewDetails?: boolean;
  onDeleted?: () => void;
  onCancelError?: (message: string | undefined) => void;
}

export const AnonymizerJobActionsMenu: FC<AnonymizerJobActionsMenuProps> = ({
  job,
  includeViewDetails = false,
  onDeleted,
  onCancelError,
}) => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const cancelJobMutation = useAnonymizerCancelRunJob({
    mutation: {
      onSuccess: () => {
        queryClient.resetQueries({
          queryKey: getAnonymizerListRunJobsQueryKey(workspace),
        });
        onCancelError?.(undefined);
      },
      onError: (error) => {
        onCancelError?.(error instanceof Error ? error.message : 'Failed to cancel job');
      },
    },
  });

  const handleCancel = useCallback(async () => {
    if (!job.workspace || !job.name) return;
    try {
      onCancelError?.(undefined);
      await cancelJobMutation.mutateAsync({ workspace: job.workspace, name: job.name });
    } catch {
      // Error is surfaced via the mutation's onError callback.
    }
  }, [job.workspace, job.name, cancelJobMutation, onCancelError]);

  const isCancellable = job.status != null && CJobCancellableStatuses.includes(job.status);

  const actions: QuickActionItem[] = [
    ...(includeViewDetails
      ? [
          {
            label: 'View details',
            onSelect: () => {
              if (job.name) {
                navigate(getAnonymizerJobRoute(workspace, job.name));
              }
            },
          },
        ]
      : []),
    ...(isCancellable
      ? [
          {
            label: 'Cancel',
            onSelect: handleCancel,
          },
        ]
      : []),
    {
      label: 'Delete',
      onSelect: () => setShowDeleteModal(true),
      danger: true,
    },
  ];

  return (
    <>
      <QuickActionsMenuRoot actions={actions} />
      {showDeleteModal && (
        <DeleteJobModal
          jobs={[job]}
          onClose={() => setShowDeleteModal(false)}
          onDeleted={onDeleted}
        />
      )}
    </>
  );
};
