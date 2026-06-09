// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useJobsDeleteJob } from '@nemo/sdk/generated/platform/api';
import { getSafeSynthesizerListJobsQueryKey } from '@nemo/sdk/generated/safe-synthesizer/api';
import { SafeSynthesizerJob } from '@nemo/sdk/generated/safe-synthesizer/schema';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useQueryClient } from '@tanstack/react-query';
import { FC, useState } from 'react';

interface DeleteJobModalProps {
  jobs: SafeSynthesizerJob[];
  onClose: () => void;
}

export const DeleteJobModal: FC<DeleteJobModalProps> = ({ jobs, onClose }) => {
  const queryClient = useQueryClient();
  const workspace = useWorkspaceFromPath();
  const [deleteError, setDeleteError] = useState<string | undefined>(undefined);

  const deleteJobMutation = useJobsDeleteJob({
    mutation: {
      onSuccess: () =>
        queryClient.resetQueries({
          queryKey: getSafeSynthesizerListJobsQueryKey(workspace),
        }),
    },
  });

  const handleDelete = async () => {
    const jobsToDelete = jobs.filter((job) => job.workspace && job.name);

    if (jobsToDelete.length === 0) {
      return false;
    }

    try {
      setDeleteError(undefined);

      // Delete all jobs in parallel
      const deletePromises = jobsToDelete.map(async (job) => {
        try {
          await deleteJobMutation.mutateAsync({ workspace: job.workspace!, name: job.name });
        } catch (error) {
          throw new Error(
            `Failed to delete job "${job.name}": ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      });

      await Promise.all(deletePromises);
      onClose();
      return true;
    } catch (error) {
      setDeleteError(
        error instanceof Error
          ? error.message
          : `Failed to delete ${jobs.length > 1 ? 'some jobs' : 'job'}`
      );
      return false;
    }
  };

  const handleClose = () => {
    setDeleteError(undefined);
    onClose();
  };

  return (
    <DeleteConfirmationModal
      open={jobs.length > 0}
      onDelete={handleDelete}
      simpleConfirm
      title={`Delete ${jobs.length} Safe Synthesizer Job${jobs.length !== 1 ? 's' : ''}`}
      errorText={deleteError}
      onClose={handleClose}
    />
  );
};
