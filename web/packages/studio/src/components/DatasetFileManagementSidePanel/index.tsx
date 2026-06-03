// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { DatasetBreadcrumbs } from '@studio/components/DatasetFileManagementSidePanel/DatasetBreadcrumbs';
import { FilesetFileExplorer } from '@studio/components/filesets/FilesetFileExplorer';
import { FilesetSidePanelWrapper } from '@studio/components/filesets/FilesetSidePanelWrapper';
import type { FC } from 'react';

export interface DatasetFileManagementSidePanelProps {
  /** Whether the sidepanel is open */
  open: boolean;
  /** Dataset workspace */
  workspace: string;
  /** Dataset name */
  datasetName: string;
  /** Full dataset identifier (workspace/name) */
  datasetId: string;
  /** Current folder path (from query param or state) */
  currentFolder?: string;
  /** All files in the dataset (for navigation and search) */
  filesList: FilesetFileOutput[] | undefined;
  /** Whether data is loading */
  isLoading: boolean;
  /** Whether files are currently being fetched */
  isFilesFetching: boolean;
  /** Callback when folder path changes */
  onFolderChange: (folderPath?: string) => void;
  /** Callback when a file is selected for viewing */
  onFileSelect: (filePath: string) => void;
  /** Callback when sidepanel is closed */
  onClose: () => void;
  /** Callback when panel animation completes (for animation lifecycle management) */
  onOpenChange?: (open: boolean) => void;
}

/**
 * Reusable dataset file management sidepanel.
 *
 * Thin shim composing `FilesetSidePanelWrapper` (side-panel chrome) and
 * `FilesetFileExplorer` (pure file-browser content). The chrome renders
 * `DatasetBreadcrumbs` in `slotHeading`; the explorer owns the toolbar,
 * table, modals, and all dataset-file state.
 */
export const DatasetFileManagementSidePanel: FC<DatasetFileManagementSidePanelProps> = ({
  open,
  workspace,
  datasetName,
  datasetId,
  currentFolder,
  filesList,
  isLoading,
  isFilesFetching,
  onFolderChange,
  onFileSelect,
  onClose,
  onOpenChange,
}) => {
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      onClose();
    }
    onOpenChange?.(isOpen);
  };

  return (
    <FilesetSidePanelWrapper
      open={open}
      onOpenChange={handleOpenChange}
      slotHeading={
        <DatasetBreadcrumbs
          datasetName={datasetName}
          currentFolder={currentFolder}
          onFolderChange={onFolderChange}
        />
      }
    >
      <FilesetFileExplorer
        workspace={workspace}
        datasetName={datasetName}
        datasetId={datasetId}
        currentFolder={currentFolder}
        filesList={filesList}
        isLoading={isLoading}
        isFilesFetching={isFilesFetching}
        onFileSelect={onFileSelect}
        enabled={open}
      />
    </FilesetSidePanelWrapper>
  );
};
