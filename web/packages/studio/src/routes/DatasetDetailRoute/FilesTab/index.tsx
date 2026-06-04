// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import {
  useFilesListFilesetFiles,
  useFilesRetrieveFileset,
} from '@nemo/sdk/generated/platform/api';
import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import { Flex } from '@nvidia/foundations-react-core';
import { FilesetFilePreviewContent } from '@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent';
import {
  FilesetFileExplorer,
  type ExtraColumn,
} from '@studio/components/filesets/FilesetFileExplorer';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { DatasetSchemaEditor } from '@studio/routes/DatasetDetailRoute/DatasetSchemaEditor';
import { useCallback, useMemo, type FC } from 'react';

export interface FilesTabProps {
  workspace: string;
  datasetName: string;
  datasetId: string;
}

/**
 * Files tab for a fileset detail page. Two-column layout regardless of fileset
 * purpose:
 *   - Left: shared `FilesetFileExplorer` (browses files).
 *   - Right: purpose-specific panel. Today: `DatasetSchemaEditor` for dataset
 *     filesets only. Slot is reserved (fixed width) for model/generic UI that
 *     will land in follow-up beads.
 */
export const FilesTab: FC<FilesTabProps> = ({ workspace, datasetName, datasetId }) => {
  const { getQueryParam, setQueryParam, setQueryParams } = useQueryParams();
  const currentFolder = getQueryParam(QUERY_PARAMETERS.filesetFolder) ?? undefined;
  const selectedFilePath = getQueryParam(QUERY_PARAMETERS.file) || undefined;

  const {
    data: filesResponse,
    isPending: isFilesPending,
    isFetching: isFilesFetching,
  } = useFilesListFilesetFiles(workspace, datasetName, undefined, {
    query: { enabled: !!workspace && !!datasetName },
  });
  const filesList = filesResponse?.data;

  const { data: fileset } = useFilesRetrieveFileset(workspace, datasetName, {
    query: { enabled: !!workspace && !!datasetName },
  });

  const handleFileSelect = useCallback(
    (filePath: string) => {
      setQueryParam(QUERY_PARAMETERS.file, filePath);
    },
    [setQueryParam]
  );

  const handleClosePreview = useCallback(() => {
    // Closing the preview by clicking the dataset breadcrumb means "back to the
    // top of the dataset." Clear both the file selection and the folder scope
    // so the explorer renders at root and the URL reflects that.
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
      // When the user collapses the folder that's currently named in the URL
      // (or any ancestor of it), clear `?filesetFolder=` so URL and visual
      // state stay in sync. Expansions never write to the URL — that would
      // churn `?filesetFolder=` on every folder click.
      if (isExpanded || !currentFolder) return;
      const isCurrentOrAncestor =
        currentFolder === folderPath || currentFolder.startsWith(`${folderPath}/`);
      if (isCurrentOrAncestor) {
        setQueryParams({ [QUERY_PARAMETERS.filesetFolder]: undefined });
      }
    },
    [currentFolder, setQueryParams]
  );

  const showSchemaEditor = fileset?.purpose === FilesetPurpose.dataset;

  // Schema column for dataset filesets only. Resolves each file's mapping
  // from `metadata.dataset` so the user can see, at a glance, which schema
  // each file uses (or `default` when it falls back to the root schema).
  const datasetMetadata = fileset?.metadata?.dataset;
  const extraColumns = useMemo<ExtraColumn[] | undefined>(() => {
    if (!showSchemaEditor) return undefined;
    const schemasByPath = datasetMetadata?.schemas_by_path ?? {};
    const rootSchema = datasetMetadata?.schema;
    return [
      {
        header: 'Schema',
        width: 140,
        cell: (node) => {
          if (node.type !== 'file') return null;
          const mapped = schemasByPath[node.path];
          if (typeof mapped === 'string') return mapped;
          if (mapped && typeof mapped === 'object') return null;
          if (typeof rootSchema === 'string') return rootSchema;
          return null;
        },
      },
    ];
  }, [showSchemaEditor, datasetMetadata]);

  return (
    <Flex
      direction="row"
      gap="density-md"
      className="w-full h-full min-h-0"
      data-testid="dataset-files-tab"
    >
      <Flex direction="col" className="flex-1 min-w-0 min-h-0">
        {selectedFilePath ? (
          <div className="w-full h-full min-h-0" data-testid="dataset-files-tab-preview">
            <FilesetFilePreviewContent
              workspace={workspace}
              filesetName={datasetName}
              filePath={selectedFilePath}
              onFilesetClick={handleClosePreview}
              onFolderClick={handleFolderChange}
              onDeleteSuccess={handleClosePreview}
              onRenameSuccess={(newPath) => setQueryParam(QUERY_PARAMETERS.file, newPath)}
            />
          </div>
        ) : (
          <FilesetFileExplorer
            workspace={workspace}
            datasetName={datasetName}
            datasetId={datasetId}
            currentFolder={currentFolder}
            filesList={filesList}
            isLoading={isFilesPending}
            isFilesFetching={isFilesFetching}
            onFileSelect={handleFileSelect}
            onFolderToggle={handleFolderToggle}
            extraColumns={extraColumns}
          />
        )}
      </Flex>
      <div
        className="w-[480px] shrink-0 h-full min-h-0 flex flex-col p-density-lg"
        data-testid="dataset-files-tab-right-panel"
      >
        {showSchemaEditor && fileset && (
          <DatasetSchemaEditor
            workspace={workspace}
            datasetName={datasetName}
            fileset={fileset}
            filesList={filesList}
            selectedFilePath={selectedFilePath}
          />
        )}
      </div>
    </Flex>
  );
};
