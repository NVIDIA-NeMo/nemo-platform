// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Stack, Tag, Text } from '@nvidia/foundations-react-core';
import { FILE_FORMAT_TAG_COLOR } from '@studio/components/FileRowEditor/constants';
import type { DataFileFormat } from '@studio/components/FileRowEditor/parse';
import { Download, FileSpreadsheet, FolderOpen, Plus } from 'lucide-react';
import { type ChangeEvent, type FC, type RefObject } from 'react';

export interface FileHeaderProps {
  fileName: string;
  fileFormat: DataFileFormat;
  rowCount: number;
  columnCount: number;
  fileSizeLabel: string;
  /** Parse/load error to surface in place of the "Schema inferred" note. */
  loadError: string | null;
  /** Whether to show the "Open File" action that loads a local file in-browser. */
  showOpenFile: boolean;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileSelected: (event: ChangeEvent<HTMLInputElement>) => void;
  onOpenFileClick: () => void;
  onDownload: () => void;
  onAddRow: () => void;
  /** Disables the Download action (e.g. when there are no rows to export). */
  downloadDisabled: boolean;
}

/** Header summary + toolbar for the {@link FileRowEditor}: file identity, stats, actions. */
export const FileHeader: FC<FileHeaderProps> = ({
  fileName,
  fileFormat,
  rowCount,
  columnCount,
  fileSizeLabel,
  loadError,
  showOpenFile,
  fileInputRef,
  onFileSelected,
  onOpenFileClick,
  onDownload,
  onAddRow,
  downloadDisabled,
}) => (
  <Flex align="center" gap="density-md" className="w-full shrink-0">
    <Flex align="center" justify="center" className="size-10 shrink-0 rounded-md bg-surface-sunken">
      <FileSpreadsheet size={20} className="text-secondary" />
    </Flex>
    <Stack gap="density-xs" className="min-w-0 flex-1">
      <Flex align="center" gap="density-sm">
        <Text kind="title/xs" className="truncate">
          {fileName}
        </Text>
        <Tag kind="solid" color={FILE_FORMAT_TAG_COLOR[fileFormat]} readOnly>
          {fileFormat === 'unknown' ? 'FILE' : fileFormat.toUpperCase()}
        </Tag>
      </Flex>
      <Flex align="center" gap="density-sm" className="text-secondary">
        <Text kind="body/regular/sm" className="text-secondary">
          {rowCount.toLocaleString()} rows · {columnCount} columns · {fileSizeLabel}
        </Text>
        <Text kind="body/regular/sm" className="text-secondary">
          ·
        </Text>
        {loadError ? (
          <Text kind="body/regular/sm" className="text-danger">
            {loadError}
          </Text>
        ) : (
          <Text kind="body/regular/sm" className="text-secondary">
            Schema inferred
          </Text>
        )}
      </Flex>
    </Stack>
    <Flex align="center" gap="density-sm" className="shrink-0">
      {showOpenFile && (
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.jsonl,.ndjson,.csv"
            className="hidden"
            aria-hidden="true"
            tabIndex={-1}
            onChange={onFileSelected}
          />
          <Button kind="secondary" color="neutral" onClick={onOpenFileClick}>
            <FolderOpen size={16} />
            Open File
          </Button>
        </>
      )}
      <Button kind="secondary" color="neutral" onClick={onDownload} disabled={downloadDisabled}>
        <Download size={16} />
        Download
      </Button>
      <Button kind="primary" color="brand" onClick={onAddRow}>
        <Plus size={16} />
        Add Row
      </Button>
    </Flex>
  </Flex>
);
