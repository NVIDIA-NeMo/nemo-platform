// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useFilesRetrieveFileset } from '@nemo/sdk/generated/platform/api';
import { Button, Flex, Spinner, Stack, Table, Text } from '@nvidia/foundations-react-core';
import { PENDING_FILE_OID } from '@studio/components/filesets/FilesetFileExplorer/constants';
import { DatasetFileDropzone } from '@studio/components/filesets/FilesetFileExplorer/DatasetFileDropzone';
import { FilesetFileExplorerEmptyState } from '@studio/components/filesets/FilesetFileExplorer/FilesetFileExplorerEmptyState';
import { FilesetFileExplorerModals } from '@studio/components/filesets/FilesetFileExplorer/FilesetFileExplorerModals';
import { FilesetFileExplorerToolbar } from '@studio/components/filesets/FilesetFileExplorer/FilesetFileExplorerToolbar';
import { useFileActions } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileActions';
import { useFileSelection } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileSelection';
import { useFileUpload } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileUpload';
import type {
  ExtraColumn,
  FilesetFileExplorerProps,
} from '@studio/components/filesets/FilesetFileExplorer/types';
import { useFilesetFileExplorerColumns } from '@studio/components/filesets/FilesetFileExplorer/useFilesetFileExplorerColumns';
import { useFilesetFileExplorerRows } from '@studio/components/filesets/FilesetFileExplorer/useFilesetFileExplorerRows';
import { useBulkDownload } from '@studio/components/filesets/hooks/useBulkDownload';
import { useBulkDuplicate } from '@studio/components/filesets/hooks/useBulkDuplicate';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { useDatasetNavigator } from '@studio/hooks/useDatasetNavigator';
import { X } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type { ExtraColumn, FilesetFileExplorerProps };

export const FilesetFileExplorer: FC<FilesetFileExplorerProps> = ({
  workspace,
  datasetName,
  datasetId,
  currentFolder,
  filesList,
  isLoading,
  isFilesFetching,
  onFileSelect,
  enabled = true,
  extraColumns,
  onFolderToggle,
}) => {
  const { data: dataset } = useFilesRetrieveFileset(workspace, datasetName, {
    query: { enabled },
  });
  const isReadWriteDataset = dataset?.storage?.type === 'local';

  const folderContents = useDatasetNavigator(filesList, currentFolder ?? '');

  const {
    handleUpload,
    isUploading,
    pendingUploads,
    pendingDuplicates,
    confirmDuplicateUpload,
    cancelDuplicateUpload,
  } = useFileUpload({
    workspace,
    datasetName,
    currentFolder,
    filesList,
  });

  const {
    sortOrder,
    sortFiles,
    searchQuery,
    handleSearchQueryChange,
    rowContents,
    treeRows,
    expandedFolders,
    toggleFolderExpand,
  } = useFileActions({
    filesList,
    isUploading,
    isFilesFetching,
    pendingUploads,
    pendingFileOid: PENDING_FILE_OID,
  });

  const autoExpandedForFolderRef = useRef<string | null>(null);
  useEffect(() => {
    const key = currentFolder ?? '';
    if (!key || autoExpandedForFolderRef.current === key) return;
    autoExpandedForFolderRef.current = key;
    const segments = key.split('/').filter(Boolean);
    let acc = '';
    for (const segment of segments) {
      acc = acc ? `${acc}/${segment}` : segment;
      if (!expandedFolders.has(acc)) toggleFolderExpand(acc);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to currentFolder changes
  }, [currentFolder]);

  const handleUserFolderToggle = useCallback(
    (path: string) => {
      const willBeExpanded = !expandedFolders.has(path);
      toggleFolderExpand(path);
      onFolderToggle?.(path, willBeExpanded);
    },
    [expandedFolders, toggleFolderExpand, onFolderToggle]
  );

  const { selectedItems, addSelectedItem, removeSelectedItem, clearSelectedItems, selectAllItems } =
    useFileSelection(rowContents, currentFolder, datasetId);

  const [addToFolderOpen, setAddToFolderOpen] = useState(false);
  const [newDirectoryOpen, setNewDirectoryOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [stagedUploadFiles, setStagedUploadFiles] = useState<File[]>([]);

  const handleUploadIntent = useCallback((files: File[]) => {
    setStagedUploadFiles(files);
    setUploadModalOpen(true);
  }, []);

  const handleOpenUploadModal = useCallback(() => {
    setStagedUploadFiles([]);
    setUploadModalOpen(true);
  }, []);

  const handleConfirmUpload = useCallback(
    async (files: File[], destinationFolder: string | undefined) => {
      await handleUpload(files, destinationFolder);
      setUploadModalOpen(false);
    },
    [handleUpload]
  );

  const { handleBulkDownload, isDownloading } = useBulkDownload({ workspace, datasetName });
  const { handleBulkDuplicate, isDuplicating } = useBulkDuplicate({ workspace, datasetName });

  const selectedFiles = useMemo(
    () => selectedItems.filter((item): item is FileSystemFile => item.type === 'file'),
    [selectedItems]
  );
  const allSelectedAreFiles =
    selectedItems.length > 0 && selectedFiles.length === selectedItems.length;

  const columns = useFilesetFileExplorerColumns({
    selectedItems,
    rowContents,
    selectAllItems,
    clearSelectedItems,
    sortFiles,
    sortOrder,
    extraColumns,
  });

  const rows = useFilesetFileExplorerRows({
    treeRows,
    expandedFolders,
    handleUserFolderToggle,
    datasetId,
    currentFolder,
    onFileSelect,
    isReadWriteDataset,
    selectedItems,
    addSelectedItem,
    removeSelectedItem,
    searchQuery,
    extraColumns,
  });

  return (
    <DatasetFileDropzone
      onUpload={handleUploadIntent}
      datasetName={datasetName}
      disabled={!isReadWriteDataset}
    >
      {(openFileDialog) => (
        <>
          {isLoading ? (
            <Flex className="h-full w-full" justify="center" align="center">
              <Spinner description="Loading files..." />
            </Flex>
          ) : (
            <>
              <Stack
                gap="density-md"
                className={
                  rowContents.length ? 'min-h-0 flex flex-col' : 'h-full min-h-0 flex flex-col'
                }
              >
                <FilesetFileExplorerToolbar
                  selectedItems={selectedItems}
                  selectedFiles={selectedFiles}
                  allSelectedAreFiles={allSelectedAreFiles}
                  isReadWriteDataset={isReadWriteDataset}
                  workspace={workspace}
                  datasetName={datasetName}
                  clearSelectedItems={clearSelectedItems}
                  isDuplicating={isDuplicating}
                  handleBulkDuplicate={handleBulkDuplicate}
                  isDownloading={isDownloading}
                  handleBulkDownload={handleBulkDownload}
                  onMove={() => setAddToFolderOpen(true)}
                  searchQuery={searchQuery}
                  handleSearchQueryChange={handleSearchQueryChange}
                  onNewDirectory={() => setNewDirectoryOpen(true)}
                  onUploadFile={handleOpenUploadModal}
                />
                {searchQuery && (
                  <Flex align="center" gap="density-md" className="w-full shrink-0">
                    <Text kind="title/xs" className="text-nowrap shrink-0">
                      {rowContents.length}&nbsp;{`Result${rowContents.length !== 1 ? 's' : ''}`}
                    </Text>
                    <Button
                      size="small"
                      kind="tertiary"
                      onClick={() => handleSearchQueryChange('', clearSelectedItems)}
                      data-testid="dataset-details-clear-filters"
                    >
                      <X className="text-brand" /> Clear filters
                    </Button>
                  </Flex>
                )}
                {!rowContents.length ? (
                  <FilesetFileExplorerEmptyState
                    searchQuery={searchQuery}
                    isReadWriteDataset={isReadWriteDataset}
                    onNewDirectory={() => setNewDirectoryOpen(true)}
                    onUploadFile={handleOpenUploadModal}
                  />
                ) : (
                  <Flex className="w-full overflow-hidden border-base border-1 rounded-lg">
                    <Table className="w-full" columns={columns} rows={rows} />
                  </Flex>
                )}
              </Stack>
              <FilesetFileExplorerModals
                newDirectoryOpen={newDirectoryOpen}
                setNewDirectoryOpen={setNewDirectoryOpen}
                addToFolderOpen={addToFolderOpen}
                setAddToFolderOpen={setAddToFolderOpen}
                uploadModalOpen={uploadModalOpen}
                setUploadModalOpen={setUploadModalOpen}
                workspace={workspace}
                datasetName={datasetName}
                currentFolder={currentFolder}
                folderContents={folderContents}
                selectedItems={selectedItems}
                clearSelectedItems={clearSelectedItems}
                pendingDuplicates={pendingDuplicates}
                confirmDuplicateUpload={confirmDuplicateUpload}
                cancelDuplicateUpload={cancelDuplicateUpload}
                isUploading={isUploading}
                stagedUploadFiles={stagedUploadFiles}
                filesList={filesList}
                openFileDialog={openFileDialog}
                handleConfirmUpload={handleConfirmUpload}
              />
            </>
          )}
        </>
      )}
    </DatasetFileDropzone>
  );
};
