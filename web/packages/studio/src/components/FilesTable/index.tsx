// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ScrollTable } from '@nemo/common/src/components/ScrollTable';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useQueryParams } from '@nemo/common/src/hooks/useQueryParams';
import { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { Flex, Stack, TableRowDefinition } from '@nvidia/foundations-react-core';
import { DirectoryQuickActions } from '@studio/components/FilesTable/DirectoryQuickActions';
import { FileQuickActions } from '@studio/components/FilesTable/FileQuickActions';
import { FileSystemNode } from '@studio/components/FilesTable/utils';
import { useDatasetNavigator } from '@studio/hooks/useDatasetNavigator';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { getFilesetFileRoute } from '@studio/routes/utils';
import { getHumanReadableFileSize } from '@studio/util/files';
import { File, FolderClosed } from 'lucide-react';
import { FC, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

interface Props {
  filesList: FilesetFileOutput[];
  datasetFullName: string;
  isLoading?: boolean;
}

export const FilesTable: FC<Props> = ({ filesList, datasetFullName, isLoading }) => {
  const { getQueryParam, setQueryParam } = useQueryParams();
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();

  const currentFolder = getQueryParam(QUERY_PARAMETERS.filesetFolder);
  const folderContents = useDatasetNavigator(filesList, currentFolder ?? '');

  const handleDirectoryClick = useCallback(
    (path: string) => {
      setQueryParam(QUERY_PARAMETERS.filesetFolder, path);
    },
    [setQueryParam]
  );

  const onRowClick = useCallback(
    (row: FileSystemNode) => {
      if (row.type === 'directory') {
        // Navigate into the directory
        handleDirectoryClick(row.path);
      } else if (row.type === 'file') {
        // for json, jsonl file, just open the viewer
        const extension = row.path.split('.').pop();
        if (extension && ['json', 'jsonl'].includes(extension)) {
          const { path } = row;
          const to = getFilesetFileRoute(workspace, datasetFullName, path);
          navigate(to);
        }
      }
    },
    [datasetFullName, handleDirectoryClick, navigate, workspace]
  );

  const rows = useMemo<TableRowDefinition[]>(
    () =>
      folderContents?.map((file) => ({
        id: `${file.type}=${file.path}`,
        cells: [
          {
            children: (
              <Flex gap="density-sm" align="center">
                {file.type === 'directory' ? <FolderClosed /> : <File />}
                <div>{file.path.split('/').pop()}</div>
              </Flex>
            ),
          },
          {
            children: file.type === 'file' ? getHumanReadableFileSize(file.size) : null,
          },
          {
            children:
              file.type === 'file' || file.type === 'directory' ? (
                <span onClick={(e) => e.stopPropagation()}>
                  {file.type === 'file' ? (
                    <FileQuickActions file={file} datasetId={datasetFullName} />
                  ) : (
                    <DirectoryQuickActions directory={file} datasetId={datasetFullName} />
                  )}
                </span>
              ) : undefined,
            attributes: {
              TableDataCell: {
                style: { textOverflow: 'clip' },
                align: 'center',
              },
            },
          },
        ],
        onRowSelect: () => onRowClick(file),
        attributes: {
          TableRow: { className: 'cursor-pointer hover:bg-accent-gray-subtle' },
        },
      })) || [],
    [datasetFullName, folderContents, onRowClick]
  );

  return (
    <Stack gap="density-lg" className="flex-1 h-full overflow-y-auto" justify="center">
      <ScrollTable
        columns={[
          {
            children: 'Name',
          },
          {
            children: 'Size',
          },
          {
            children: 'Actions',
            attributes: {
              TableHeaderCell: {
                style: { width: 80, textAlign: 'center', textOverflow: 'clip' },
              },
            },
          },
        ]}
        rows={rows}
        pagination={false}
        loading={isLoading}
        slotEmptyState={
          <TableEmptyState
            header="No files"
            emptyMessage="Upload a file to this dataset to view it here."
          />
        }
      />
    </Stack>
  );
};
