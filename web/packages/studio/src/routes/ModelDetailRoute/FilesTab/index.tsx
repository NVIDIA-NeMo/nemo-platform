// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { Flex, Text } from '@nvidia/foundations-react-core';
import { FilesetFilePreviewContent } from '@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent';
import { FilesetFileExplorer } from '@studio/components/filesets/FilesetFileExplorer';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { useCallback, type FC } from 'react';

export interface FilesTabProps {
  workspace: string;
  modelName: string;
  modelId: string;
  files: FilesetFileOutput[] | undefined;
  isFilesError: boolean;
  isFilesFetching: boolean;
}

export const FilesTab: FC<FilesTabProps> = ({
  workspace,
  modelName,
  modelId,
  files,
  isFilesError,
  isFilesFetching,
}) => {
  const { getQueryParam, setQueryParam, setQueryParams } = useQueryParams();
  const currentFolder = getQueryParam(QUERY_PARAMETERS.filesetFolder) ?? undefined;
  const selectedFilePath = getQueryParam(QUERY_PARAMETERS.file) || undefined;

  const handleFileSelect = useCallback(
    (filePath: string) => {
      setQueryParam(QUERY_PARAMETERS.file, filePath);
    },
    [setQueryParam]
  );

  const handleClosePreview = useCallback(() => {
    setQueryParams({
      [QUERY_PARAMETERS.file]: undefined,
      [QUERY_PARAMETERS.filesetFolder]: undefined,
    });
  }, [setQueryParams]);

  const handleFolderChange = useCallback(
    (folderPath: string) => {
      setQueryParams({
        [QUERY_PARAMETERS.file]: undefined,
        [QUERY_PARAMETERS.filesetFolder]: folderPath || undefined,
      });
    },
    [setQueryParams]
  );

  const handleFolderToggle = useCallback(
    (folderPath: string, isExpanded: boolean) => {
      if (isExpanded || !currentFolder) return;
      const isCurrentOrAncestor =
        currentFolder === folderPath || currentFolder.startsWith(`${folderPath}/`);
      if (isCurrentOrAncestor) {
        setQueryParams({ [QUERY_PARAMETERS.filesetFolder]: undefined });
      }
    },
    [currentFolder, setQueryParams]
  );

  if (isFilesError) {
    return (
      <Flex
        className="w-full min-h-80"
        align="center"
        justify="center"
        data-testid="model-files-tab"
      >
        <Text className="text-feedback-danger">Failed to load model files.</Text>
      </Flex>
    );
  }

  return (
    <Flex
      direction="row"
      gap="density-md"
      className="w-full h-full min-h-0"
      data-testid="model-files-tab"
    >
      <Flex direction="col" className="flex-1 min-w-0 min-h-0">
        {selectedFilePath ? (
          <div className="w-full h-full min-h-0" data-testid="model-files-tab-preview">
            <FilesetFilePreviewContent
              workspace={workspace}
              filesetName={modelName}
              filePath={selectedFilePath}
              onFilesetClick={handleClosePreview}
              onFolderClick={handleFolderChange}
              onDeleteSuccess={handleClosePreview}
              onRenameSuccess={(newPath) => setQueryParam(QUERY_PARAMETERS.file, newPath)}
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto">
            <FilesetFileExplorer
              workspace={workspace}
              datasetName={modelName}
              datasetId={modelId}
              currentFolder={currentFolder}
              filesList={files}
              isLoading={false}
              isFilesFetching={isFilesFetching}
              onFileSelect={handleFileSelect}
              onFolderToggle={handleFolderToggle}
            />
          </div>
        )}
      </Flex>
    </Flex>
  );
};
