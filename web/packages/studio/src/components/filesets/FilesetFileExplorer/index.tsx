// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useFilesRetrieveFileset } from '@nemo/sdk/generated/platform/api';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import {
  Anchor,
  Button,
  Checkbox,
  Flex,
  ProgressBar,
  Spinner,
  Stack,
  Table,
  type TableRowDefinition,
  TableToolbar,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { AddToFolderModal } from '@studio/components/filesets/AddToFolderModal';
import { BulkDeleteModal } from '@studio/components/filesets/FilesetFileExplorer/BulkDeleteModal';
import { DatasetFileDropzone } from '@studio/components/filesets/FilesetFileExplorer/DatasetFileDropzone';
import { DuplicateFileConfirmationModal } from '@studio/components/filesets/FilesetFileExplorer/DuplicateFileConfirmationModal';
import { useFileActions } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileActions';
import { useFileSelection } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileSelection';
import { useFileUpload } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileUpload';
import { NewDirectoryModal } from '@studio/components/filesets/FilesetFileExplorer/NewDirectoryModal';
import { UploadToFolderModal } from '@studio/components/filesets/FilesetFileExplorer/UploadToFolderModal';
import { useBulkDownload } from '@studio/components/filesets/hooks/useBulkDownload';
import { useBulkDuplicate } from '@studio/components/filesets/hooks/useBulkDuplicate';
import { DirectoryQuickActions } from '@studio/components/FilesTable/DirectoryQuickActions';
import { FileQuickActions } from '@studio/components/FilesTable/FileQuickActions';
import type { FileSystemFile, FileSystemNode } from '@studio/components/FilesTable/utils';
import { useDatasetNavigator } from '@studio/hooks/useDatasetNavigator';
import { getFolderSize, getHumanReadableFileSize } from '@studio/util/files';
import { getTextWithCount } from '@studio/util/strings';
import {
  ArrowDown,
  ArrowUp,
  Copy,
  Download,
  X,
  File,
  FolderClosed,
  FolderOpen,
  Search,
  Trash,
} from 'lucide-react';
import { type FC, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const PENDING_FILE_OID = '------PENDING------';
const getItemId = (item: FileSystemNode) => [item.oid, item.type, item.path].join('-');

/**
 * Optional extra column injected by a consumer of FilesetFileExplorer.
 * Each extra column is appended after the built-in Name and Size columns
 * and rendered before the trailing quick-actions column.
 *
 * The cell renderer receives every FileSystemNode (files AND directories);
 * return null for nodes that should render nothing.
 */
export interface ExtraColumn {
  header: ReactNode;
  cell: (node: FileSystemNode) => ReactNode;
  /** Optional fixed header-cell width in px. */
  width?: number;
}

export interface FilesetFileExplorerProps {
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
  /** Whether file-list data is loading */
  isLoading: boolean;
  /** Whether files are currently being fetched */
  isFilesFetching: boolean;
  /** Callback when a file is selected for viewing. When omitted, file rows are
   *  non-interactive (no row-click navigation, no "View File" quick action).
   *  Hosts that don't yet have a preview surface should leave this undefined
   *  rather than passing a no-op, so the view affordance isn't exposed. */
  onFileSelect?: (filePath: string) => void;
  /** Gates the fileset metadata fetch. Defaults to true.
   *  Hosts that mount the explorer behind a panel animation can pass the panel's
   *  open state to suppress fetches while closed. */
  enabled?: boolean;
  /** Purpose-specific columns appended after Name + Size and before quick-actions.
   *  Hosts use this to inject domain columns (e.g. dataset Schema) without
   *  pushing dataset-specific knowledge into the shared explorer. */
  extraColumns?: ExtraColumn[];
  /** Fires when the user explicitly toggles a folder open or closed (row click).
   *  Does NOT fire for the explorer's own auto-expansion from `currentFolder`.
   *  Hosts can use this to sync URL state (e.g. drop `?filesetFolder=` when the
   *  user collapses the folder that was named in the URL). */
  onFolderToggle?: (folderPath: string, isExpanded: boolean) => void;
}

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
  // Dataset storage type: local and s3 are read/write; ngc and huggingface are read-only
  const { data: dataset } = useFilesRetrieveFileset(workspace, datasetName, {
    query: { enabled },
  });
  const isReadWriteDataset = dataset?.storage?.type === 'local' || dataset?.storage?.type === 's3';

  // Folder navigation
  const folderContents = useDatasetNavigator(filesList, currentFolder ?? '');

  // File upload
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

  // Sorting, searching, and row computation
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

  // When the consumer mounts us with a `currentFolder` set (e.g. via URL state
  // restored from a file-preview breadcrumb click), auto-expand that folder and
  // every ancestor so the user sees the location they navigated to. Guarded by
  // a ref so React 18 strict-mode double-invocation doesn't collapse what it
  // just expanded.
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

  // User-initiated folder toggle: same internal state mutation, but also fires
  // the consumer's `onFolderToggle` so it can sync external state (e.g. URL).
  // Distinct from auto-expand so URL state isn't churned by the explorer's
  // own restoration of `currentFolder`.
  const handleUserFolderToggle = useCallback(
    (path: string) => {
      const willBeExpanded = !expandedFolders.has(path);
      toggleFolderExpand(path);
      onFolderToggle?.(path, willBeExpanded);
    },
    [expandedFolders, toggleFolderExpand, onFolderToggle]
  );

  // File selection
  const { selectedItems, addSelectedItem, removeSelectedItem, clearSelectedItems, selectAllItems } =
    useFileSelection(rowContents, currentFolder, datasetId);

  // Add to folder modal state
  const [addToFolderOpen, setAddToFolderOpen] = useState(false);
  // New directory modal state
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

  // Bulk download (files only)
  const { handleBulkDownload, isDownloading } = useBulkDownload({ workspace, datasetName });
  // Bulk duplicate (files only)
  const { handleBulkDuplicate, isDuplicating } = useBulkDuplicate({ workspace, datasetName });

  // Non-delete bulk actions (Download, Add to Folder, …) are only available when
  // every selected item is a file. Mixed file/directory selections expose Delete only.
  const selectedFiles = useMemo(
    () => selectedItems.filter((item): item is FileSystemFile => item.type === 'file'),
    [selectedItems]
  );
  const allSelectedAreFiles =
    selectedItems.length > 0 && selectedFiles.length === selectedItems.length;

  // Table columns
  const columns = useMemo(
    () => [
      {
        children: (
          <Checkbox
            checked={
              selectedItems.length === rowContents.length
                ? true
                : selectedItems.length > 0
                  ? 'indeterminate'
                  : false
            }
            onCheckedChange={(checked) => {
              if (checked) {
                selectAllItems();
              } else {
                clearSelectedItems();
              }
            }}
            attributes={{
              CheckboxInput: {
                'aria-label': `Select all files and directories`,
                'aria-labelledby': undefined,
              },
            }}
          />
        ),
        attributes: {
          TableHeaderCell: { style: { width: 48 } },
        },
      },
      {
        children: (
          <Button type="button" kind="tertiary" onClick={() => sortFiles('name')}>
            Name
            {sortOrder.sortBy === 'name' &&
              (sortOrder.order === 'asc' ? <ArrowUp /> : <ArrowDown />)}
          </Button>
        ),
      },
      {
        children: (
          <Button type="button" kind="tertiary" onClick={() => sortFiles('size')}>
            Size
            {sortOrder.sortBy === 'size' &&
              (sortOrder.order === 'asc' ? <ArrowUp /> : <ArrowDown />)}
          </Button>
        ),
      },
      ...(extraColumns ?? []).map((col) => ({
        children: col.header,
        attributes:
          col.width !== undefined
            ? { TableHeaderCell: { style: { width: col.width } } }
            : undefined,
      })),
      {
        children: <></>,
        attributes: {
          TableHeaderCell: { style: { width: 58 } },
        },
      },
    ],
    [
      selectedItems,
      rowContents,
      selectAllItems,
      clearSelectedItems,
      sortFiles,
      sortOrder,
      extraColumns,
    ]
  );

  const INDENT_PER_LEVEL = 20;

  // Table rows
  const rows: TableRowDefinition[] = useMemo(
    () =>
      treeRows.map(({ node, depth }) => ({
        id: getItemId(node),
        cells: [
          {
            children: (
              <Checkbox
                disabled={node.oid === PENDING_FILE_OID}
                checked={selectedItems.includes(node)}
                onCheckedChange={(checked) => {
                  if (checked) {
                    addSelectedItem(node);
                  } else {
                    removeSelectedItem(node);
                  }
                }}
                attributes={{
                  CheckboxInput: {
                    'aria-label': `Select path ${node.path}`,
                    'aria-labelledby': undefined,
                  },
                }}
              />
            ),
          },
          {
            children: (
              <Flex direction="col" gap="density-xs">
                {/* eslint-disable-next-line no-restricted-syntax -- dynamic tree indent */}
                <div style={{ paddingLeft: depth * INDENT_PER_LEVEL }}>
                  <Flex gap="density-sm" align="center">
                    {node.type === 'directory' ? (
                      expandedFolders.has(node.path) ? (
                        <FolderOpen />
                      ) : (
                        <FolderClosed />
                      )
                    ) : (
                      <File />
                    )}
                    <div>{searchQuery ? node.path : node.path.split('/').pop()}</div>
                  </Flex>
                </div>
                {node.oid === PENDING_FILE_OID && (
                  <ProgressBar
                    kind="indeterminate"
                    size="small"
                    aria-label="Uploading..."
                    className="mb-[-8px]"
                  />
                )}
              </Flex>
            ),
            onCellSelect: () => {
              if (node.type === 'file') {
                onFileSelect?.(node.path);
              } else if (node.type === 'directory') {
                handleUserFolderToggle(node.path);
              }
            },
            attributes: {
              TableDataCell: {
                // Directories always toggle on click; files only do so when a
                // view handler is wired up. Skip the pointer cursor for files
                // without a handler so the row doesn't look interactive.
                className: node.type === 'directory' || onFileSelect ? 'cursor-pointer' : undefined,
              },
            },
          },
          {
            children:
              node.type === 'file' ? getHumanReadableFileSize(node.size) : getFolderSize(node),
          },
          ...(extraColumns ?? []).map((col) => ({
            children: col.cell(node),
          })),
          {
            children:
              node.oid === PENDING_FILE_OID ? null : node.type === 'file' ? (
                <FileQuickActions
                  file={node}
                  datasetId={datasetId}
                  currentFolder={currentFolder}
                  onViewFile={onFileSelect}
                  isReadWriteDataset={isReadWriteDataset}
                />
              ) : node.type === 'directory' ? (
                <DirectoryQuickActions
                  directory={node}
                  datasetId={datasetId}
                  currentFolder={currentFolder}
                />
              ) : null,
            attributes: {
              TableDataCell: {
                style: { textOverflow: 'clip' },
                align: 'center',
                className: 'h-[59px]',
              },
            },
          },
        ],
      })),
    [
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
    ]
  );

  return (
    <DatasetFileDropzone onUpload={handleUploadIntent} datasetName={datasetName}>
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
                <TableToolbar
                  aria-label="Dataset files toolbar"
                  className="min-w-0 shrink-0"
                  showBulkActionsToolbar={selectedItems.length > 0}
                  slotBulkActions={
                    <Flex
                      align="center"
                      justify="between"
                      className="w-full"
                      data-testid="dataset-files-selection-bar"
                    >
                      <Text kind="body/regular/md">
                        {getTextWithCount('row', selectedItems.length, 'rows')} selected
                      </Text>
                      <Flex align="center" gap="density-md">
                        {isReadWriteDataset ? (
                          <BulkDeleteModal
                            selectedItems={selectedItems}
                            workspace={workspace}
                            datasetName={datasetName}
                            onConfirmDelete={clearSelectedItems}
                            slotTrigger={
                              <Button kind="tertiary" data-testid="dataset-files-bulk-delete">
                                <Trash />
                                Delete
                              </Button>
                            }
                          />
                        ) : null}
                        {allSelectedAreFiles ? (
                          <>
                            {isReadWriteDataset ? (
                              <>
                                <Button
                                  kind="tertiary"
                                  disabled={isDuplicating}
                                  onClick={async () => {
                                    // Keep the selection on failure so the user
                                    // can retry without re-selecting.
                                    const ok = await handleBulkDuplicate(selectedFiles);
                                    if (ok) clearSelectedItems();
                                  }}
                                  data-testid="dataset-files-bulk-duplicate"
                                >
                                  <Copy />
                                  Duplicate
                                </Button>
                                <Button
                                  kind="tertiary"
                                  onClick={() => setAddToFolderOpen(true)}
                                  data-testid="dataset-files-bulk-move"
                                >
                                  <FolderOpen />
                                  Move
                                </Button>
                              </>
                            ) : null}
                            <Button
                              kind="tertiary"
                              disabled={isDownloading}
                              onClick={async () => {
                                await handleBulkDownload(selectedFiles);
                                clearSelectedItems();
                              }}
                              data-testid="dataset-files-bulk-download"
                            >
                              <Download />
                              Download
                            </Button>
                          </>
                        ) : null}
                        <Button
                          kind="tertiary"
                          onClick={clearSelectedItems}
                          data-testid="dataset-files-bulk-cancel"
                        >
                          Cancel
                        </Button>
                      </Flex>
                    </Flex>
                  }
                >
                  <Flex direction="row" gap="density-md" className="min-w-0 w-full">
                    <TextInput
                      value={searchQuery}
                      onValueChange={(value) => handleSearchQueryChange(value, clearSelectedItems)}
                      placeholder="Search"
                      slotStart={<Search />}
                      dismissible
                      data-testid="dataset-details-search-input"
                      className="min-w-0 flex-1"
                    />
                    <Flex gap="density-md" className="ml-auto">
                      <Button
                        kind="secondary"
                        onClick={() => setNewDirectoryOpen(true)}
                        data-testid="dataset-details-new-directory-button"
                      >
                        New Directory
                      </Button>
                      <Button kind="secondary" onClick={handleOpenUploadModal}>
                        Upload File
                      </Button>
                    </Flex>
                  </Flex>
                </TableToolbar>
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
                  <Flex className="min-h-0 w-full flex-1" align="center" justify="center">
                    <TableEmptyState
                      className="h-auto! max-w-full"
                      header="No Files"
                      emptyMessage={
                        searchQuery ? (
                          'No files match your search.'
                        ) : (
                          <>
                            Organize with folders or upload files by drag-and-drop or browsing.{' '}
                            <br /> Visit the docs for setup instructions.{' '}
                            <Anchor
                              href="https://docs.nvidia.com/nemo/microservices/latest/manage-entities/datasets/create-dataset.html"
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Documentation
                            </Anchor>
                          </>
                        )
                      }
                      actions={
                        searchQuery ? null : (
                          <Flex gap="density-md">
                            <Button kind="secondary" onClick={() => setNewDirectoryOpen(true)}>
                              New Directory
                            </Button>
                            <Button kind="secondary" onClick={handleOpenUploadModal}>
                              Upload File
                            </Button>
                          </Flex>
                        )
                      }
                    />
                  </Flex>
                ) : (
                  <Flex className="w-full overflow-hidden border-base border-1 rounded-lg">
                    <Table className="w-full" columns={columns} rows={rows} />
                  </Flex>
                )}
              </Stack>
              <NewDirectoryModal
                open={newDirectoryOpen}
                onClose={() => setNewDirectoryOpen(false)}
                workspace={workspace}
                datasetName={datasetName}
                currentFolder={currentFolder}
                folderContents={folderContents}
                onSuccess={() => setNewDirectoryOpen(false)}
              />
              <AddToFolderModal
                open={addToFolderOpen}
                onClose={() => setAddToFolderOpen(false)}
                selectedItems={selectedItems}
                workspace={workspace}
                datasetName={datasetName}
                currentFolder={currentFolder}
                folderContents={folderContents}
                onComplete={clearSelectedItems}
              />
              <DuplicateFileConfirmationModal
                duplicateFiles={pendingDuplicates}
                onConfirm={confirmDuplicateUpload}
                onCancel={cancelDuplicateUpload}
                isPending={isUploading}
              />
              <UploadToFolderModal
                open={uploadModalOpen}
                onClose={() => setUploadModalOpen(false)}
                files={stagedUploadFiles}
                defaultFolder={currentFolder}
                filesList={filesList}
                openFileDialog={openFileDialog}
                onConfirm={handleConfirmUpload}
              />
            </>
          )}
        </>
      )}
    </DatasetFileDropzone>
  );
};
