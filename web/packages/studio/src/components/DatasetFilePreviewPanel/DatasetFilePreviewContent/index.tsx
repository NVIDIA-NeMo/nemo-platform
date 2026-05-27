// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FileContentPreview } from '@nemo/common/src/components/FileContentPreview';
import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { Stack } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { DatasetFilePreviewHeader } from '@studio/components/DatasetFilePreviewPanel/components/DatasetFilePreviewHeader';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { useMemo, type FC } from 'react';

export interface DatasetFilePreviewContentProps {
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

  // Optional: pre-fetched data (parent already has the file + content)
  file?: FileSystemFile;
  fileContent?: string;
  isLoading?: boolean;
  error?: Error;

  /**
   * When true, the inline header (breadcrumbs + file actions) is suppressed.
   * The host is responsible for rendering equivalent affordances elsewhere
   * (e.g. a SidePanel slotHeading). Defaults to false.
   */
  hideHeader?: boolean;

  /** Whether the host considers this content active for fetching purposes. Defaults to true. */
  enabled?: boolean;
}

/**
 * Content-only variant of the dataset file preview:
 * breadcrumbs + file actions header + read-only file viewer.
 *
 * No panel chrome. Used inline from FilesTab on the dataset detail page,
 * and composed by `DatasetFilePreviewPanel` (the side-panel wrapper).
 */
export const DatasetFilePreviewContent: FC<DatasetFilePreviewContentProps> = ({
  datasetWorkspace,
  datasetName,
  filePath,
  onDatasetClick,
  onFolderClick,
  onDeleteSuccess,
  onRenameSuccess,
  file: externalFile,
  fileContent: externalContent,
  isLoading: externalLoading,
  error: externalError,
  hideHeader = false,
  enabled = true,
}) => {
  const {
    data: internalContent,
    isLoading: internalLoading,
    error: internalError,
  } = useDatasetFileContent({
    workspace: datasetWorkspace,
    name: datasetName,
    path: filePath,
    enabled: !externalContent && enabled,
  });

  const { data: allFilesResponse } = useFilesListFilesetFiles(
    datasetWorkspace,
    datasetName,
    undefined,
    { query: { enabled: !externalFile && enabled } }
  );
  const allFiles = allFilesResponse?.data;

  const fileContent = externalContent ?? internalContent;
  const isLoading = externalLoading ?? internalLoading;
  const error = externalError ?? internalError;
  const file =
    externalFile ?? (allFiles?.find((f) => f.path === filePath) as FileSystemFile | undefined);

  const body = useMemo(
    () => (
      <FileContentPreview
        file={{ path: filePath }}
        content={fileContent}
        isLoading={isLoading}
        error={error ?? null}
      />
    ),
    [filePath, fileContent, isLoading, error]
  );

  if (hideHeader) {
    return body;
  }

  return (
    <Stack gap="density-sm" className="h-full min-h-0">
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
      <div className="flex-1 min-h-0">{body}</div>
    </Stack>
  );
};
