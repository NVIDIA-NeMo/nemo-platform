// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EntityEmptyState } from '@nemo/common/src/components/EntityEmptyState';
import { Flex } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

export interface FilesetFileExplorerEmptyStateProps {
  hasSearchApplied: boolean;
  isReadWriteDataset: boolean;
  onUploadFile: () => void;
  onClearSearch: () => void;
}

export const FilesetFileExplorerEmptyState: FC<FilesetFileExplorerEmptyStateProps> = ({
  hasSearchApplied,
  isReadWriteDataset,
  onUploadFile,
  onClearSearch,
}) => (
  <Flex className="min-h-0 w-full flex-1" align="center" justify="center">
    {hasSearchApplied ? (
      <EntityEmptyState entity="filesetFiles" variant="no-results" onClearFilters={onClearSearch} />
    ) : (
      <EntityEmptyState
        entity="filesetFiles"
        variant="first-use"
        onCreate={isReadWriteDataset ? onUploadFile : undefined}
      />
    )}
  </Flex>
);
