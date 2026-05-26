// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { SidePanel } from '@nvidia/foundations-react-core';
import { DatasetFilePreviewHeader } from '@studio/components/DatasetFilePreviewPanel/components/DatasetFilePreviewHeader';
import { DatasetFilePreviewContent } from '@studio/components/DatasetFilePreviewPanel/DatasetFilePreviewContent';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import type { FC } from 'react';

export interface DatasetFilePreviewPanelProps {
  // Panel chrome
  open: boolean;
  onCloseClick: () => void;
  onOutsideClick?: () => void;

  // Dataset context
  datasetWorkspace: string;
  datasetName: string;
  filePath: string;

  // Navigation callbacks
  onDatasetClick?: () => void;
  onFolderClick?: (folderPath: string) => void;

  // File actions
  onDeleteSuccess?: () => void;
  onRenameSuccess?: (newPath: string) => void;

  // Optional: pre-fetched data (for performance or when parent already has data)
  file?: FileSystemFile;
  fileContent?: string;
  isLoading?: boolean;
  error?: Error;
}

/**
 * Side-panel wrapper around `DatasetFilePreviewContent`.
 *
 * Kept as a thin shim so legacy callers (`FilesetListRoute/PanelManagement`)
 * continue to render the file preview as a right-side panel. The new
 * dataset detail Files tab embeds `DatasetFilePreviewContent` inline instead.
 */
export const DatasetFilePreviewPanel: FC<DatasetFilePreviewPanelProps> = ({
  open,
  onCloseClick,
  onOutsideClick,
  datasetWorkspace,
  datasetName,
  filePath,
  onDatasetClick,
  onFolderClick,
  onDeleteSuccess,
  onRenameSuccess,
  file: externalFile,
  fileContent,
  isLoading,
  error,
}) => {
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) onCloseClick();
  };

  const handleOutside = () => {
    if (onOutsideClick) {
      onOutsideClick();
    } else {
      onCloseClick();
    }
  };

  const { data: allFilesResponse } = useFilesListFilesetFiles(
    datasetWorkspace,
    datasetName,
    undefined,
    { query: { enabled: !externalFile && open } }
  );
  const file =
    externalFile ??
    (allFilesResponse?.data?.find((f) => f.path === filePath) as FileSystemFile | undefined);

  return (
    <SidePanel
      side="right"
      open={open}
      onOpenChange={handleOpenChange}
      onEscapeKeyDown={(e) => {
        e.preventDefault();
        handleOutside();
      }}
      onPointerDownOutside={(e) => {
        e.preventDefault();
        handleOutside();
      }}
      slotHeading={
        <DatasetFilePreviewHeader
          datasetWorkspace={datasetWorkspace}
          datasetName={datasetName}
          filePath={filePath}
          file={file}
          onDatasetClick={onDatasetClick}
          onFolderClick={onFolderClick}
          onDeleteSuccess={onDeleteSuccess}
          onRenameSuccess={onRenameSuccess}
        />
      }
      attributes={{
        SidePanelHeading: { className: 'font-normal' },
      }}
      bordered
      modal
      className="max-w-[960px] w-full"
    >
      <DatasetFilePreviewContent
        datasetWorkspace={datasetWorkspace}
        datasetName={datasetName}
        filePath={filePath}
        file={file}
        fileContent={fileContent}
        isLoading={isLoading}
        error={error}
        onDatasetClick={onDatasetClick}
        onFolderClick={onFolderClick}
        onDeleteSuccess={onDeleteSuccess}
        onRenameSuccess={onRenameSuccess}
        enabled={open}
        hideHeader
      />
    </SidePanel>
  );
};
