// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useFilesDeleteFileset } from '@nemo/sdk/generated/platform/api';
import { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Modal } from '@nvidia/foundations-react-core';
import { useMutateMany } from '@studio/api/common/useMutateMany';
import { invalidateDatasetCaches } from '@studio/api/datasets/invalidateDatasetCaches';
import { logger } from '@studio/util/logger';
import { Trash } from 'lucide-react';
import { FC, ReactNode, useState } from 'react';

interface DatasetBulkDeleteModalProps {
  selectedDatasets: FilesetOutput[];
  onConfirmSuccess: () => void;
  /** Custom trigger element; when provided, used instead of the default Button */
  slotTrigger?: ReactNode;
}

export const DatasetBulkDeleteModal: FC<DatasetBulkDeleteModalProps> = ({
  selectedDatasets,
  onConfirmSuccess,
  slotTrigger,
}) => {
  const [open, setOpen] = useState<boolean>(false);

  const { mutateAsync: deleteDataset } = useFilesDeleteFileset({
    mutation: {
      onSuccess: (_data, variables) => {
        invalidateDatasetCaches(variables.workspace, variables.name, ['list']);
      },
    },
  });
  const { mutateAsync: deleteDatasets, isPending } = useMutateMany(deleteDataset);

  const handleDelete = async () => {
    try {
      const datasetsToDelete = selectedDatasets.filter(
        (dataset) => dataset.workspace && dataset.name
      );
      await deleteDatasets(
        datasetsToDelete.map((dataset) => ({
          workspace: dataset.workspace,
          name: dataset.name,
        }))
      );

      onConfirmSuccess();
      setOpen(false);
    } catch (error) {
      logger.error('Failed to delete datasets', error);
    }
  };

  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      slotTrigger={
        slotTrigger ?? (
          <Button kind="secondary" data-testid="bulk-delete-modal-trigger-button">
            <Trash />
            Delete
          </Button>
        )
      }
      slotHeading={`Delete ${selectedDatasets.length} Dataset${selectedDatasets.length > 1 ? 's' : ''}`}
      slotFooter={
        <Flex justify="end" gap="density-xs" align="center" className="w-full">
          <Button onClick={() => setOpen(false)} kind="tertiary" color="neutral">
            Cancel
          </Button>
          <Button color="danger" onClick={handleDelete} disabled={isPending}>
            {isPending ? 'Deleting...' : 'Delete'}
          </Button>
        </Flex>
      }
    >
      Are you sure you want to delete this?
    </Modal>
  );
};
