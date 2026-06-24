// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { Anchor, Button, Flex } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

export interface FilesetFileExplorerEmptyStateProps {
  searchQuery: string;
  isReadWriteDataset: boolean;
  onNewDirectory: () => void;
  onUploadFile: () => void;
}

export const FilesetFileExplorerEmptyState: FC<FilesetFileExplorerEmptyStateProps> = ({
  searchQuery,
  isReadWriteDataset,
  onNewDirectory,
  onUploadFile,
}) => (
  <Flex className="min-h-0 w-full flex-1" align="center" justify="center">
    <TableEmptyState
      className="h-auto! max-w-full"
      header="No Files"
      emptyMessage={
        searchQuery ? (
          'No files match your search.'
        ) : isReadWriteDataset ? (
          <>
            Organize with folders or upload files by drag-and-drop or browsing. <br /> Visit the
            docs for setup instructions.{' '}
            <Anchor
              href="https://docs.nvidia.com/nemo/microservices/latest/manage-entities/datasets/create-dataset.html"
              target="_blank"
              rel="noopener noreferrer"
            >
              Documentation
            </Anchor>
          </>
        ) : (
          'This fileset is read-only.'
        )
      }
      actions={
        searchQuery || !isReadWriteDataset ? null : (
          <Flex gap="density-md">
            <Button kind="secondary" onClick={onNewDirectory}>
              New Directory
            </Button>
            <Button kind="secondary" onClick={onUploadFile}>
              Upload File
            </Button>
          </Flex>
        )
      }
    />
  </Flex>
);
