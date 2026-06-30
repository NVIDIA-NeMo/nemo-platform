// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getDataDesignerListCreateJobsQueryKey,
  useDataDesignerDeleteCreateJob,
} from '@nemo/sdk/generated/data-designer/api';
import type { CreateJob as DataDesignerJob } from '@nemo/sdk/generated/data-designer/schema';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useQueryClient } from '@tanstack/react-query';
import { FC, useState } from 'react';

interface DeleteJobModalProps {
  jobs: DataDesignerJob[];
  onClose: () => void;
  onDeleted?: () => void;
}

export const DeleteJobModal: FC<DeleteJobModalProps> = ({ jobs, onClose, onDeleted }) => {
  const queryClient = useQueryClient();
  const workspace = useWorkspaceFromPath();
  const [deleteError, setDeleteError] = useState<string | undefined>(undefined);

  const deleteJobMutation = useDataDesignerDeleteCreateJob({
    mutation: {
      onSuccess: () =>
        queryClient.resetQueries({
          queryKey: getDataDesignerListCreateJobsQueryKey(workspace),
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
      onDeleted?.();
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
      title={`Delete ${jobs.length} Data Designer Job${jobs.length !== 1 ? 's' : ''}`}
      errorText={deleteError}
      onClose={handleClose}
    />
  );
};
