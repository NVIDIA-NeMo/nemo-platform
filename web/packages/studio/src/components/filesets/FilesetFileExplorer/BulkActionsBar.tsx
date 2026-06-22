// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Text } from '@nvidia/foundations-react-core';
import { useDatasetFilesDelete } from '@studio/api/datasets/useDatasetFilesDelete';
import { BulkDeleteModal } from '@studio/components/BulkDeleteModal';
import { extractFilePathsFromDirectory } from '@studio/components/filesets/FilesetFileExplorer/extractFilePathsFromDirectory';
import type { FileSystemFile, FileSystemNode } from '@studio/components/FilesTable/utils';
import { getTextWithCount } from '@studio/util/strings';
import { Copy, Download, FolderOpen, Trash } from 'lucide-react';
import { type FC, useState } from 'react';

export interface BulkActionsBarProps {
  selectedItems: FileSystemNode[];
  selectedFiles: FileSystemFile[];
  allSelectedAreFiles: boolean;
  isReadWriteDataset: boolean;
  workspace: string;
  datasetName: string;
  clearSelectedItems: () => void;
  isDuplicating: boolean;
  handleBulkDuplicate: (files: FileSystemFile[]) => Promise<boolean>;
  isDownloading: boolean;
  handleBulkDownload: (files: FileSystemFile[]) => Promise<void>;
  onMove: () => void;
}

export const BulkActionsBar: FC<BulkActionsBarProps> = ({
  selectedItems,
  selectedFiles,
  allSelectedAreFiles,
  isReadWriteDataset,
  workspace,
  datasetName,
  clearSelectedItems,
  isDuplicating,
  handleBulkDuplicate,
  isDownloading,
  handleBulkDownload,
  onMove,
}) => {
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const { mutateAsync: deleteFiles } = useDatasetFilesDelete();

  const handleBulkDelete = async (items: FileSystemNode[]) => {
    const directFilePaths = items.filter((item) => item.type === 'file').map((item) => item.path);
    const directoryFilePaths = items
      .filter((item) => item.type === 'directory')
      .flatMap((directory) => extractFilePathsFromDirectory(directory));
    const allFilePaths = [...directFilePaths, ...directoryFilePaths];
    if (allFilePaths.length > 0) {
      await deleteFiles({ workspace, datasetName, paths: allFilePaths });
    }
  };

  return (
    <Flex
      align="center"
      justify="between"
      className="w-full"
      data-testid="dataset-files-selection-bar"
    >
      <Text kind="body/regular/md">
        {getTextWithCount('row', selectedItems.length, 'rows')} selected
      </Text>
      <Flex align="center" gap="density-md">
        {isReadWriteDataset ? (
          <Button
            kind="tertiary"
            data-testid="dataset-files-bulk-delete"
            onClick={() => setBulkDeleteOpen(true)}
          >
            <Trash />
            Delete
          </Button>
        ) : null}
        {allSelectedAreFiles ? (
          <>
            {isReadWriteDataset ? (
              <>
                <Button
                  kind="tertiary"
                  disabled={isDuplicating}
                  onClick={async () => {
                    const ok = await handleBulkDuplicate(selectedFiles);
                    if (ok) clearSelectedItems();
                  }}
                  data-testid="dataset-files-bulk-duplicate"
                >
                  <Copy />
                  Duplicate
                </Button>
                <Button kind="tertiary" onClick={onMove} data-testid="dataset-files-bulk-move">
                  <FolderOpen />
                  Move
                </Button>
              </>
            ) : null}
            <Button
              kind="tertiary"
              disabled={isDownloading}
              onClick={async () => {
                await handleBulkDownload(selectedFiles);
                clearSelectedItems();
              }}
              data-testid="dataset-files-bulk-download"
            >
              <Download />
              Download
            </Button>
          </>
        ) : null}
        <Button
          kind="tertiary"
          onClick={clearSelectedItems}
          data-testid="dataset-files-bulk-cancel"
        >
          Cancel
        </Button>
      </Flex>
      <BulkDeleteModal
        items={selectedItems}
        open={bulkDeleteOpen}
        onDelete={handleBulkDelete}
        title={(count) => `Delete ${count} Item${count !== 1 ? 's' : ''}`}
        onClose={() => {
          setBulkDeleteOpen(false);
          clearSelectedItems();
        }}
      />
    </Flex>
  );
};
