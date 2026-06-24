// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AddToFolderModal } from '@studio/components/filesets/AddToFolderModal';
import { DuplicateFileConfirmationModal } from '@studio/components/filesets/FilesetFileExplorer/DuplicateFileConfirmationModal';
import { NewDirectoryModal } from '@studio/components/filesets/FilesetFileExplorer/NewDirectoryModal';
import { UploadToFolderModal } from '@studio/components/filesets/FilesetFileExplorer/UploadToFolderModal';
import type { ComponentProps, FC } from 'react';

export interface FilesetFileExplorerModalsProps {
  newDirectoryOpen: boolean;
  setNewDirectoryOpen: (open: boolean) => void;
  addToFolderOpen: boolean;
  setAddToFolderOpen: (open: boolean) => void;
  uploadModalOpen: boolean;
  setUploadModalOpen: (open: boolean) => void;
  workspace: string;
  datasetName: string;
  currentFolder?: string;
  folderContents: ComponentProps<typeof NewDirectoryModal>['folderContents'];
  selectedItems: ComponentProps<typeof AddToFolderModal>['selectedItems'];
  clearSelectedItems: () => void;
  pendingDuplicates: ComponentProps<typeof DuplicateFileConfirmationModal>['duplicateFiles'];
  confirmDuplicateUpload: ComponentProps<typeof DuplicateFileConfirmationModal>['onConfirm'];
  cancelDuplicateUpload: ComponentProps<typeof DuplicateFileConfirmationModal>['onCancel'];
  isUploading: boolean;
  stagedUploadFiles: File[];
  filesList: ComponentProps<typeof UploadToFolderModal>['filesList'];
  openFileDialog: ComponentProps<typeof UploadToFolderModal>['openFileDialog'];
  handleConfirmUpload: ComponentProps<typeof UploadToFolderModal>['onConfirm'];
}

export const FilesetFileExplorerModals: FC<FilesetFileExplorerModalsProps> = ({
  newDirectoryOpen,
  setNewDirectoryOpen,
  addToFolderOpen,
  setAddToFolderOpen,
  uploadModalOpen,
  setUploadModalOpen,
  workspace,
  datasetName,
  currentFolder,
  folderContents,
  selectedItems,
  clearSelectedItems,
  pendingDuplicates,
  confirmDuplicateUpload,
  cancelDuplicateUpload,
  isUploading,
  stagedUploadFiles,
  filesList,
  openFileDialog,
  handleConfirmUpload,
}) => (
  <>
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
);
