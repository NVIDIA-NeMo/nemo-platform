// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex } from '@nvidia/foundations-react-core';
import { FileActions } from '@studio/components/DatasetFilePreviewPanel/components/FileActions';
import { FileBreadcrumbs } from '@studio/components/DatasetFilePreviewPanel/components/FileBreadcrumbs';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { FolderOpen } from 'lucide-react';
import type { FC } from 'react';

export interface DatasetFilePreviewHeaderProps {
  datasetWorkspace: string;
  datasetName: string;
  filePath: string;
  /** Resolved file used to render delete/rename/split actions. Omit to hide actions. */
  file?: FileSystemFile;
  onDatasetClick?: () => void;
  onFolderClick?: (folderPath: string) => void;
  onDeleteSuccess?: () => void;
  onRenameSuccess?: (newPath: string) => void;
}

export const DatasetFilePreviewHeader: FC<DatasetFilePreviewHeaderProps> = ({
  datasetWorkspace,
  datasetName,
  filePath,
  file,
  onDatasetClick,
  onFolderClick,
  onDeleteSuccess,
  onRenameSuccess,
}) => (
  <Flex justify="between" align="center" gap="density-sm" className="shrink-0 w-full">
    <Flex gap="density-sm" align="center" className="min-w-0">
      <FolderOpen width={16} height={16} />
      <FileBreadcrumbs
        datasetName={datasetName}
        filePath={filePath}
        onDatasetClick={onDatasetClick}
        onFolderClick={onFolderClick}
      />
    </Flex>
    {file && (
      <FileActions
        file={file}
        datasetWorkspace={datasetWorkspace}
        datasetName={datasetName}
        onDeleteSuccess={onDeleteSuccess}
        onRenameSuccess={onRenameSuccess}
      />
    )}
  </Flex>
);
