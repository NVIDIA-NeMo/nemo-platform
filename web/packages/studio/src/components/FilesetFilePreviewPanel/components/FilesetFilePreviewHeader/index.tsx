// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex } from '@nvidia/foundations-react-core';
import { FileBreadcrumbs } from '@studio/components/FilesetFilePreviewPanel/components/FileBreadcrumbs';
import { FileQuickActions } from '@studio/components/FilesTable/FileQuickActions';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { FolderOpen } from 'lucide-react';
import type { FC } from 'react';

export interface FilesetFilePreviewHeaderProps {
  workspace: string;
  filesetName: string;
  filePath: string;
  /** Resolved file used to render delete/rename/split actions. Omit to hide actions. */
  file?: FileSystemFile;
  /** When true, show the full action menu (Move, Duplicate, Create Split, Transform, Rename). */
  isReadWriteDataset?: boolean;
  /**
   * `inline` (default) keeps the actions menu in flow at the end of the header row.
   * `overlay` pins it to the SidePanel heading's absolute close button so the two
   * line up; the host must reserve the horizontal space (see `SIDE_PANEL_HEADING_CLASS`).
   */
  actionsPlacement?: 'inline' | 'overlay';
  onFilesetClick?: () => void;
  onFolderClick?: (folderPath: string) => void;
  onDeleteSuccess?: () => void;
  onRenameSuccess?: (newPath: string) => void;
}

/**
 * Padding the SidePanel heading needs so the breadcrumbs stop before the overlaid
 * actions menu (48px button at `right-19`) instead of running underneath it.
 */
export const SIDE_PANEL_HEADING_CLASS = 'font-normal pr-32';

/** Mirrors `.nv-side-panel-close`'s offsets so the menu sits level with the close button. */
const OVERLAY_ACTIONS_CLASS =
  'absolute top-[calc(var(--heading-padding-block)-1px)] right-19 translate-y-[-25%]';

export const FilesetFilePreviewHeader: FC<FilesetFilePreviewHeaderProps> = ({
  workspace,
  filesetName,
  filePath,
  file,
  isReadWriteDataset = true,
  actionsPlacement = 'inline',
  onFilesetClick,
  onFolderClick,
  onDeleteSuccess,
  onRenameSuccess,
}) => (
  <Flex justify="between" align="center" gap="density-sm" className="shrink-0 w-full">
    <Flex gap="density-sm" align="center" className="min-w-0">
      <FolderOpen className="shrink-0" width={16} height={16} />
      <FileBreadcrumbs
        filesetName={filesetName}
        filePath={filePath}
        onFilesetClick={onFilesetClick}
        onFolderClick={onFolderClick}
      />
    </Flex>
    {file && (
      <div className={actionsPlacement === 'overlay' ? OVERLAY_ACTIONS_CLASS : 'shrink-0'}>
        <FileQuickActions
          file={file}
          datasetId={`${workspace}/${filesetName}`}
          isReadWriteDataset={isReadWriteDataset}
          onDeleteSuccess={onDeleteSuccess}
          onRenameSuccess={onRenameSuccess}
        />
      </div>
    )}
  </Flex>
);
