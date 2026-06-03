// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { useFilesListFilesetFiles } from '@nemo/sdk/generated/platform/api';
import { Flex } from '@nvidia/foundations-react-core';
import { FilesetFilePreviewContent } from '@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent';
import { FilesetFileExplorer } from '@studio/components/filesets/FilesetFileExplorer';
import { useWorkspaceFromPathOrProp } from '@studio/hooks/useWorkspaceFromPath';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { useCallback, type FC } from 'react';

export interface FilesTabProps {
  workspace?: string;
  filesetName: string;
  filesetId: string;
}

/**
 * Files tab for the fileset detail page. Single-column layout that mirrors the
 * side panel's Files view: the shared {@link FilesetFileExplorer} swaps to an
 * inline {@link FilesetFilePreviewContent} when a file is selected (tracked via
 * the `?file=` query param), instead of opening a separate preview panel.
 */
export const FilesTab: FC<FilesTabProps> = ({ workspace, filesetName, filesetId }) => {
  const usedWs = useWorkspaceFromPathOrProp(workspace);
  const { getQueryParam, setQueryParam, setQueryParams } = useQueryParams();
  const currentFolder = getQueryParam(QUERY_PARAMETERS.filesetFolder) ?? undefined;
  const selectedFilePath = getQueryParam(QUERY_PARAMETERS.file) || undefined;

  const {
    data: filesResponse,
    isPending: isFilesPending,
    isFetching: isFilesFetching,
  } = useFilesListFilesetFiles(usedWs, filesetName, undefined, {
    query: { enabled: !!usedWs && !!filesetName },
  });
  const filesList = filesResponse?.data;

  const handleFileSelect = useCallback(
    (filePath: string) => {
      setQueryParam(QUERY_PARAMETERS.file, filePath);
    },
    [setQueryParam]
  );

  const handleClosePreview = useCallback(() => {
    // Closing the preview via the fileset breadcrumb means "back to the top of
    // the fileset." Clear both the file selection and the folder scope so the
    // explorer renders at root and the URL reflects that.
    setQueryParams({
      [QUERY_PARAMETERS.file]: undefined,
      [QUERY_PARAMETERS.filesetFolder]: undefined,
    });
  }, [setQueryParams]);

  const handleFolderChange = useCallback(
    (folderPath: string) => {
      // Folder breadcrumb click inside the preview: clear the file selection
      // and navigate the explorer to that folder, atomically.
      setQueryParams({
        [QUERY_PARAMETERS.file]: undefined,
        [QUERY_PARAMETERS.filesetFolder]: folderPath || undefined,
      });
    },
    [setQueryParams]
  );

  const handleFolderToggle = useCallback(
    (folderPath: string, isExpanded: boolean) => {
      // When the user collapses the folder named in the URL (or an ancestor of
      // it), clear `?filesetFolder=` so URL and visual state stay in sync.
      // Expansions never write to the URL — that would churn the param on every
      // folder click.
      if (isExpanded || !currentFolder) return;
      const isCurrentOrAncestor =
        currentFolder === folderPath || currentFolder.startsWith(`${folderPath}/`);
      if (isCurrentOrAncestor) {
        setQueryParams({ [QUERY_PARAMETERS.filesetFolder]: undefined });
      }
    },
    [currentFolder, setQueryParams]
  );

  return (
    <Flex
      direction="col"
      className="w-full h-full min-h-0 overflow-auto"
      data-testid="fileset-files-tab"
    >
      {selectedFilePath ? (
        <div className="w-full h-full min-h-0" data-testid="fileset-files-tab-preview">
          <FilesetFilePreviewContent
            workspace={usedWs}
            filesetName={filesetName}
            filePath={selectedFilePath}
            onFilesetClick={handleClosePreview}
            onFolderClick={handleFolderChange}
            onDeleteSuccess={handleClosePreview}
            onRenameSuccess={(newPath) => setQueryParam(QUERY_PARAMETERS.file, newPath)}
          />
        </div>
      ) : (
        <FilesetFileExplorer
          workspace={usedWs}
          datasetName={filesetName}
          datasetId={filesetId}
          currentFolder={currentFolder}
          filesList={filesList}
          isLoading={isFilesPending}
          isFilesFetching={isFilesFetching}
          onFileSelect={handleFileSelect}
          onFolderToggle={handleFolderToggle}
        />
      )}
    </Flex>
  );
};
