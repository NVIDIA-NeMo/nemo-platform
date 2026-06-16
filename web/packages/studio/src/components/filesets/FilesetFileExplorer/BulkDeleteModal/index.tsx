// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Modal } from '@nvidia/foundations-react-core';
import { useDatasetFilesDelete } from '@studio/api/datasets/useDatasetFilesDelete';
import { extractFilePathsFromDirectory } from '@studio/components/filesets/FilesetFileExplorer/BulkDeleteModal/utils';
import { FileSystemNode } from '@studio/components/FilesTable/utils';
import { logger } from '@studio/util/logger';
import { Trash } from 'lucide-react';
import { FC, ReactNode, useState } from 'react';

interface BulkDeleteModalProps {
  selectedItems: FileSystemNode[];
  workspace: string;
  datasetName: string;
  onConfirmDelete: () => void;
  /** Custom trigger; defaults to a secondary Button */
  slotTrigger?: ReactNode;
}

export const BulkDeleteModal: FC<BulkDeleteModalProps> = ({
  selectedItems,
  workspace,
  datasetName,
  onConfirmDelete,
  slotTrigger,
}) => {
  const [open, setOpen] = useState<boolean>(false);

  // Separate files and directories for display purposes
  const files = selectedItems.filter((item) => item.type === 'file');
  const directories = selectedItems.filter((item) => item.type === 'directory');

  const { mutateAsync: deleteFiles, isPending } = useDatasetFilesDelete();

  const handleDelete = async () => {
    try {
      // Collect all file paths from directly selected files
      const directFilePaths = files.map((file) => file.path);

      // Extract all file paths from selected directories
      const directoryFilePaths = directories.flatMap((directory) =>
        extractFilePathsFromDirectory(directory)
      );

      // Combine all file paths for a single deletion operation
      const allFilePaths = [...directFilePaths, ...directoryFilePaths];

      if (allFilePaths.length > 0) {
        await deleteFiles({
          workspace,
          datasetName,
          paths: allFilePaths,
        });
      }
      onConfirmDelete();
      setOpen(false);
    } catch (error) {
      // Error handling is managed by the mutation hooks
      logger.error('Failed to delete items', error);
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
      slotHeading={`Delete ${selectedItems.length} Item${selectedItems.length > 1 ? 's' : ''}`}
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
