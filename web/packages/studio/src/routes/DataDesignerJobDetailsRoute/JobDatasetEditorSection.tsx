// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  Card,
  Flex,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  FILE_PREVIEW_MAX_BYTES,
  useDatasetFileContent,
} from '@studio/api/datasets/useDatasetFileContent';
import { useDatasetFilesUpload } from '@studio/api/datasets/useDatasetFilesUpload';
import { Empty } from '@studio/components/Empty';
import { FileRowEditor } from '@studio/components/FileRowEditor';
import {
  type DataFileFormat,
  formatFromFileName,
  parseDataFile,
  serializeDataFile,
} from '@studio/components/FileRowEditor/parse';
import type { DataFileRow } from '@studio/components/FileRowEditor/types';
import { BUILDER_CONFIG_FILENAME } from '@studio/routes/DataDesignerJobDetailsRoute/builderConfig';
import { useDataDesignerArtifactsFileset } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerArtifactsFileset';
import { getFileNameFromPath, getHumanReadableFileSize } from '@studio/util/files';
import { useCallback, useEffect, useMemo, useRef, useState, type FC, type ReactNode } from 'react';

/** File formats this tab can render as rows. Parquet is decoded to JSONL by the hook. */
const DATA_FILE_FORMATS: readonly DataFileFormat[] = ['parquet', 'jsonl', 'json', 'csv'];

/**
 * Suffix for the JSONL file that holds edits to a Parquet source. Parquet cannot be
 * re-encoded in the browser, so edits are persisted to a sibling JSONL file instead of
 * corrupting the original `.parquet`.
 */
const PARQUET_EDIT_SUFFIX = '.edited.jsonl';

const parquetEditSiblingPath = (path: string): string =>
  `${path.replace(/\.[^./]+$/, '')}${PARQUET_EDIT_SUFFIX}`;

const centered = (children: ReactNode) => (
  <Card>
    <Stack
      align="center"
      justify="center"
      gap="density-md"
      className="h-full min-h-0 min-w-0 w-full"
    >
      {children}
    </Stack>
  </Card>
);

/**
 * "Data" tab for a Data Designer job: browses the generated data files in the job's
 * output fileset and renders the selected file in the {@link FileRowEditor}. Content is
 * fetched via {@link useDatasetFileContent}, which decodes Parquet to JSONL server-side,
 * so Parquet/JSONL/JSON/CSV all arrive as text and parse through {@link parseDataFile}.
 *
 * Edits are persisted via the editor's "Save File" action: text formats (JSON/JSONL/CSV)
 * overwrite the file in place, while Parquet — which cannot be re-encoded in-browser — is
 * saved to a sibling JSONL file that then becomes the default/selected view.
 */
export const JobDatasetEditorSection: FC = () => {
  const { filesetWorkspace, filesetName, files, isResultsLoading, isFilesLoading } =
    useDataDesignerArtifactsFileset();

  // Data files only — exclude the builder config and any non-row formats.
  const dataFiles = useMemo(
    () =>
      files.filter(
        (file) =>
          file.path !== BUILDER_CONFIG_FILENAME &&
          !file.path.endsWith(`/${BUILDER_CONFIG_FILENAME}`) &&
          DATA_FILE_FORMATS.includes(formatFromFileName(file.path))
      ),
    [files]
  );

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const pendingSiblingPath = useRef<string | null>(null);

  const defaultPath = useMemo(() => {
    const editSibling = dataFiles.find((file) => file.path.endsWith(PARQUET_EDIT_SUFFIX));
    if (editSibling) {
      return editSibling.path;
    }
    const firstParquet = dataFiles.find((file) => formatFromFileName(file.path) === 'parquet');
    return firstParquet?.path ?? dataFiles[0]?.path ?? null;
  }, [dataFiles]);

  // Default once files resolve; keep the current pick if it survives (or is a pending save).
  useEffect(() => {
    setSelectedPath((prev) => {
      if (prev && dataFiles.some((file) => file.path === prev)) {
        // Once the pending sibling shows up in the list, it no longer needs the guard.
        if (prev === pendingSiblingPath.current) {
          pendingSiblingPath.current = null;
        }
        return prev;
      }
      if (prev && prev === pendingSiblingPath.current) {
        return prev;
      }
      return defaultPath;
    });
  }, [dataFiles, defaultPath]);

  const selectedFile = useMemo(
    () => dataFiles.find((file) => file.path === selectedPath) ?? null,
    [dataFiles, selectedPath]
  );

  const sourceFormat: DataFileFormat = selectedPath ? formatFromFileName(selectedPath) : 'unknown';
  // The hook returns Parquet content already decoded to JSONL, so parse it as JSONL.
  const parseFormat: DataFileFormat = sourceFormat === 'parquet' ? 'jsonl' : sourceFormat;

  const {
    data: rawContent,
    isLoading: isContentLoading,
    isError: isContentError,
  } = useDatasetFileContent({
    workspace: filesetWorkspace,
    name: filesetName,
    path: selectedPath ?? '',
    enabled: Boolean(filesetWorkspace && filesetName && selectedPath),
  });

  const parsed = useMemo(() => {
    if (rawContent == null) {
      return null;
    }
    try {
      return { rows: parseDataFile(rawContent, parseFormat), error: null as string | null };
    } catch (error) {
      return {
        rows: [],
        error: error instanceof Error ? error.message : 'Failed to parse file.',
      };
    }
  }, [rawContent, parseFormat]);

  const isContentTruncated = Boolean(
    selectedFile && sourceFormat !== 'parquet' && selectedFile.size > FILE_PREVIEW_MAX_BYTES
  );
  const saveDisabledReason = isContentTruncated
    ? 'This file is too large to load in full — saving is disabled to avoid truncating it.'
    : undefined;

  const toast = useToast();
  const { mutateAsync: uploadFiles, isPending: isSaving } = useDatasetFilesUpload();

  const handleSaveFile = useCallback(
    async (rows: DataFileRow[]) => {
      if (!filesetWorkspace || !filesetName || !selectedPath) {
        return;
      }
      const isParquetSource = sourceFormat === 'parquet';
      const targetPath = isParquetSource ? parquetEditSiblingPath(selectedPath) : selectedPath;
      const targetFormat: DataFileFormat = isParquetSource ? 'jsonl' : sourceFormat;
      const content = serializeDataFile(rows, targetFormat);
      const file = new File([content], targetPath, { type: 'application/octet-stream' });

      try {
        await uploadFiles({
          workspace: filesetWorkspace,
          datasetName: filesetName,
          files: [file],
        });
        if (isParquetSource) {
          pendingSiblingPath.current = targetPath;
          setSelectedPath(targetPath);
          toast.success(`Saved edits to ${getFileNameFromPath(targetPath)}`);
        } else {
          toast.success('File saved');
        }
      } catch (error) {
        toast.error('Could not save file. Your changes were not persisted.');
        throw error;
      }
    },
    [filesetWorkspace, filesetName, selectedPath, sourceFormat, uploadFiles, toast]
  );

  const isResolving = isResultsLoading || isFilesLoading;

  const fileSelector =
    dataFiles.length > 1 ? (
      <Flex align="center" gap="density-sm" className="shrink-0">
        <Text kind="label/semibold/sm" className="text-secondary">
          File
        </Text>
        <SelectRoot
          value={selectedPath ?? defaultPath ?? undefined}
          onValueChange={(value: string) => setSelectedPath(value)}
        >
          <SelectTrigger
            placeholder="Select a file"
            renderValue={(value) =>
              typeof value === 'string' ? (
                <span className="block max-w-[200px] truncate text-left [direction:rtl]">
                  {getFileNameFromPath(value)}
                </span>
              ) : null
            }
          />
          <SelectContent className="w-(--radix-popper-anchor-width)">
            <SelectListbox>
              {dataFiles.map((file) => (
                <SelectItem key={file.path} value={file.path}>
                  {getFileNameFromPath(file.path)}
                </SelectItem>
              ))}
            </SelectListbox>
          </SelectContent>
        </SelectRoot>
      </Flex>
    ) : null;

  const renderBody = () => {
    if (isResolving && dataFiles.length === 0) {
      return centered(<Spinner aria-label="Loading job data" description="Loading job data..." />);
    }

    if (dataFiles.length === 0) {
      return centered(
        <Empty
          title="No data files were found in this job's output fileset."
          description="Generated data appears here once the job has produced its artifacts."
        />
      );
    }

    if (isContentLoading || parsed == null) {
      return centered(<Spinner aria-label="Loading file" description="Loading file..." />);
    }

    if (isContentError) {
      return centered(
        <Empty
          title="Could not load file"
          description="The selected file could not be downloaded from the Files service."
        />
      );
    }

    if (parsed.error) {
      return centered(<Empty title="Could not parse file" description={parsed.error} />);
    }

    return (
      <FileRowEditor
        key={selectedPath}
        fileName={selectedPath ?? undefined}
        fileSizeLabel={selectedFile ? getHumanReadableFileSize(selectedFile.size) : undefined}
        initialRows={parsed.rows}
        showOpenFile={false}
        onSaveFile={handleSaveFile}
        isSaving={isSaving}
        saveDisabledReason={saveDisabledReason}
      />
    );
  };

  return (
    <Stack gap="density-md" className="h-full min-h-0 min-w-0 w-full">
      {fileSelector ? (
        <Flex align="center" justify="start" className="shrink-0">
          {fileSelector}
        </Flex>
      ) : null}
      <Stack className="min-h-0 min-w-0 w-full flex-1">{renderBody()}</Stack>
    </Stack>
  );
};
