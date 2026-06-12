// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parseFilesetLocation } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useDataDesignerListCreateJobResults } from '@nemo/sdk/generated/data-designer/api';
import type { CreateJob as DataDesignerJob } from '@nemo/sdk/generated/data-designer/schema';
import {
  getFilesListFilesetFilesQueryKey,
  useFilesListFilesetFiles,
  useFilesRetrieveFileset,
} from '@nemo/sdk/generated/platform/api';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { Anchor, Banner, Card, Stack, Text } from '@nvidia/foundations-react-core';
import { FilesetFilePreviewPanel } from '@studio/components/FilesetFilePreviewPanel';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { getFilesetDetailsRoute } from '@studio/routes/utils';
import { getHumanReadableFileSize } from '@studio/util/files';
import { useQueryClient } from '@tanstack/react-query';
import { ComponentProps, FC, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const ARTIFACTS_RESULT_NAME = 'artifacts';

type FileRow = FilesetFileOutput & { id: string };

interface JobOutputFilesetSectionProps {
  workspace: string;
  jobName: string;
  job: DataDesignerJob;
}

function fileRowToSystemFile(row: FileRow): FileSystemFile {
  return {
    type: 'file',
    path: row.path,
    size: row.size,
    oid: row.file_ref,
  };
}

export const JobOutputFilesetSection: FC<JobOutputFilesetSectionProps> = ({
  workspace,
  jobName,
  job,
}) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewFile, setPreviewFile] = useState<FileSystemFile | null>(null);

  const isTerminal = job.status != null && PlatformJobTerminalStatuses.includes(job.status);

  const { data: resultsResponse, isLoading: isResultsLoading } =
    useDataDesignerListCreateJobResults(workspace, jobName, {
      query: {
        refetchInterval: isTerminal ? false : 3000,
      },
    });

  const artifactsResult = useMemo(() => {
    const data = resultsResponse?.data;
    if (!data?.length) {
      return undefined;
    }
    const preferred = data.find((r) => r.name === ARTIFACTS_RESULT_NAME);
    if (preferred) {
      return preferred;
    }
    return data.find((r) => r.artifact_url && parseFilesetLocation(r.artifact_url, workspace));
  }, [resultsResponse?.data, workspace]);

  const filesetLoc = useMemo(
    () =>
      artifactsResult?.artifact_url
        ? parseFilesetLocation(artifactsResult.artifact_url, workspace)
        : null,
    [artifactsResult?.artifact_url, workspace]
  );

  const filesetWorkspace = filesetLoc?.workspace ?? '';
  const filesetName = filesetLoc?.name ?? '';
  const listFilesParams = useMemo(
    () => (filesetLoc?.filesListPathPrefix ? { path: filesetLoc.filesListPathPrefix } : undefined),
    [filesetLoc?.filesListPathPrefix]
  );

  const {
    data: filesetMeta,
    isLoading: isFilesetLoading,
    isError: isFilesetError,
    error: filesetError,
  } = useFilesRetrieveFileset(filesetWorkspace, filesetName, {
    query: {
      enabled: Boolean(filesetWorkspace && filesetName),
    },
  });

  const {
    data: listFilesResponse,
    isLoading: isFilesLoading,
    isError: isListFilesError,
    error: listFilesError,
  } = useFilesListFilesetFiles(filesetWorkspace, filesetName, listFilesParams, {
    query: {
      enabled: Boolean(filesetWorkspace && filesetName),
    },
  });

  const dataViewState = useStudioDataViewState({
    defaultPageSize: 10,
  });

  const rows: FileRow[] = useMemo(() => {
    const fileList = listFilesResponse?.data ?? [];
    return fileList.map((f) => ({ ...f, id: f.file_ref }));
  }, [listFilesResponse?.data]);

  const makeColumns: ComponentProps<typeof StudioDataView<FileRow>>['makeColumns'] = useMemo(
    () => (helpers) => [
      helpers.accessor('path', {
        header: 'Path',
        cell: ({ row }) => (
          <Text kind="body/regular/md" className="font-mono text-sm">
            {row.original.path}
          </Text>
        ),
      }),
      helpers.accessor('size', {
        header: 'Size',
        size: 120,
        cell: ({ row }) => (
          <Text kind="body/regular/md">{getHumanReadableFileSize(row.original.size)}</Text>
        ),
      }),
    ],
    []
  );

  const invalidateFilesetFileQueries = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: getFilesListFilesetFilesQueryKey(filesetWorkspace, filesetName, listFilesParams),
    });
  }, [queryClient, filesetWorkspace, filesetName, listFilesParams]);

  const handlePreviewClose = useCallback(() => {
    setPreviewFile(null);
  }, []);

  const handleRowClick = useCallback((row: FileRow) => {
    setPreviewFile(fileRowToSystemFile(row));
  }, []);

  const handleDatasetClickFromPreview = useCallback(() => {
    navigate(getFilesetDetailsRoute(filesetWorkspace, encodeURIComponent(filesetName)));
  }, [navigate, filesetWorkspace, filesetName]);

  const handleFolderClickFromPreview = useCallback(
    (folderPath: string) => {
      navigate(
        getFilesetDetailsRoute(
          filesetWorkspace,
          encodeURIComponent(filesetName),
          encodeURIComponent(folderPath)
        )
      );
    },
    [navigate, filesetWorkspace, filesetName]
  );

  const handleFileDeleteSuccess = useCallback(() => {
    setPreviewFile(null);
    invalidateFilesetFileQueries();
  }, [invalidateFilesetFileQueries]);

  const handleFileRenameSuccess = useCallback(
    (newPath: string) => {
      setPreviewFile((prev) => (prev ? { ...prev, path: newPath } : null));
      invalidateFilesetFileQueries();
    },
    [invalidateFilesetFileQueries]
  );

  useEffect(() => {
    if (!filesetWorkspace || !filesetName) {
      setPreviewFile(null);
    }
  }, [filesetWorkspace, filesetName]);

  if (isResultsLoading && !resultsResponse) {
    return (
      <Card>
        <Stack gap="4" padding="8">
          <Text kind="body/regular/md" className="text-muted">
            Loading job results…
          </Text>
        </Stack>
      </Card>
    );
  }

  if (!artifactsResult) {
    return (
      <Card>
        <Stack gap="4" padding="8">
          <Text kind="body/bold/lg">Output fileset</Text>
          <Text kind="body/regular/md" className="text-muted">
            {isTerminal
              ? 'No artifacts result was returned for this job.'
              : 'Output files will appear here once the job registers its artifacts result.'}
          </Text>
        </Stack>
      </Card>
    );
  }

  if (!filesetLoc) {
    return (
      <Card>
        <Stack gap="4" padding="8">
          <Text kind="body/bold/lg">Output fileset</Text>
          <KVPair
            label="Artifact URL"
            value={artifactsResult.artifact_url}
            orientation="vertical"
          />
        </Stack>
      </Card>
    );
  }

  const filesErr = filesetError ?? listFilesError;
  const filesServiceError =
    isFilesetError || isListFilesError
      ? filesErr instanceof Error
        ? filesErr.message
        : 'Could not load fileset or file list from the Files service.'
      : null;

  return (
    <>
      <Card>
        <Stack gap="2" padding="2">
          <Stack gap="2">
            <Text kind="body/bold/lg">Output fileset</Text>
            <Text kind="body/regular/sm" className="text-muted">
              Generated data for this job is stored in the following workspace fileset.
            </Text>
          </Stack>

          {filesServiceError != null && (
            <Banner kind="inline" status="error" title="Files service error">
              {filesServiceError}
            </Banner>
          )}

          <Stack gap="4">
            <KVPair
              label="Fileset"
              value={
                <Anchor>
                  <Link
                    to={getFilesetDetailsRoute(
                      filesetWorkspace,
                      encodeURIComponent(filesetWorkspace + '/' + filesetName)
                    )}
                  >
                    {filesetName}
                  </Link>
                </Anchor>
              }
            />
            {filesetMeta?.description?.trim() ? (
              <KVPair label="Description" value={filesetMeta.description} orientation="vertical" />
            ) : null}
          </Stack>

          <Stack gap="4">
            <Text kind="label/semibold/md">Files</Text>
            <Text kind="body/regular/sm" className="text-muted">
              Select a row to preview the file.
            </Text>
            <StudioDataView<FileRow>
              dataViewState={dataViewState}
              makeColumns={makeColumns}
              onRowClick={handleRowClick}
              attributes={{
                DataViewRoot: {
                  data: rows,
                  totalCount: rows.length,
                  requestStatus: isFilesetLoading || isFilesLoading ? 'loading' : undefined,
                },
                DataViewTableContent: {
                  className: 'studio-data-view-table',
                  renderEmptyState: () => (
                    <TableEmptyState
                      className="py-4"
                      header="No files yet"
                      emptyMessage="This fileset has no files, or they are not visible yet."
                    />
                  ),
                },
              }}
            />
          </Stack>
        </Stack>
      </Card>

      <FilesetFilePreviewPanel
        open={previewFile != null}
        onCloseClick={handlePreviewClose}
        onOutsideClick={handlePreviewClose}
        workspace={filesetWorkspace}
        filesetName={filesetName}
        filePath={previewFile?.path ?? ''}
        file={previewFile ?? undefined}
        onFilesetClick={handleDatasetClickFromPreview}
        onFolderClick={handleFolderClickFromPreview}
        onDeleteSuccess={handleFileDeleteSuccess}
        onRenameSuccess={handleFileRenameSuccess}
      />
    </>
  );
};
