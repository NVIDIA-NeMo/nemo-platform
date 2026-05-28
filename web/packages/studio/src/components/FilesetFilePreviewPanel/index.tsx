// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { SidePanel } from '@nvidia/foundations-react-core';
import { FilesetFilePreviewHeader } from '@studio/components/FilesetFilePreviewPanel/components/FilesetFilePreviewHeader';
import { FilesetFilePreviewContent } from '@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import type { FC } from 'react';

export interface FilesetFilePreviewPanelProps {
  // Panel chrome
  open: boolean;
  onCloseClick: () => void;
  onOutsideClick?: () => void;

  // Fileset context
  workspace: string;
  filesetName: string;
  filePath: string;

  // Navigation callbacks
  onFilesetClick?: () => void;
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
 * Side-panel wrapper around `FilesetFilePreviewContent`.
 *
 * Kept as a thin shim so legacy callers (`FilesetListRoute/PanelManagement`)
 * continue to render the file preview as a right-side panel. The newer
 * fileset detail Files tabs (dataset, model) embed `FilesetFilePreviewContent`
 * inline instead.
 */
export const FilesetFilePreviewPanel: FC<FilesetFilePreviewPanelProps> = ({
  open,
  onCloseClick,
  onOutsideClick,
  workspace,
  filesetName,
  filePath,
  onFilesetClick,
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

  const { data: allFilesResponse } = useFilesListFilesetFiles(workspace, filesetName, undefined, {
    query: { enabled: !externalFile && open },
  });
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
        <FilesetFilePreviewHeader
          workspace={workspace}
          filesetName={filesetName}
          filePath={filePath}
          file={file}
          onFilesetClick={onFilesetClick}
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
      <FilesetFilePreviewContent
        workspace={workspace}
        filesetName={filesetName}
        filePath={filePath}
        file={file}
        fileContent={fileContent}
        isLoading={isLoading}
        error={error}
        onFilesetClick={onFilesetClick}
        onFolderClick={onFolderClick}
        onDeleteSuccess={onDeleteSuccess}
        onRenameSuccess={onRenameSuccess}
        enabled={open}
        hideHeader
      />
    </SidePanel>
  );
};
