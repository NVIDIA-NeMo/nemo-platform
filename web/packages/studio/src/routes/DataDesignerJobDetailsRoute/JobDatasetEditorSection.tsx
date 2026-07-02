// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

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
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { Empty } from '@studio/components/Empty';
import { FileRowEditor } from '@studio/components/FileRowEditor';
import {
  type DataFileFormat,
  formatFromFileName,
  parseDataFile,
} from '@studio/components/FileRowEditor/parse';
import { BUILDER_CONFIG_FILENAME } from '@studio/routes/DataDesignerJobDetailsRoute/builderConfig';
import { useDataDesignerArtifactsFileset } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerArtifactsFileset';
import { getFileNameFromPath, getHumanReadableFileSize } from '@studio/util/files';
import { useEffect, useMemo, useState, type FC, type ReactNode } from 'react';

/** File formats this tab can render as rows. Parquet is decoded to JSONL by the hook. */
const DATA_FILE_FORMATS: readonly DataFileFormat[] = ['parquet', 'jsonl', 'json', 'csv'];

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
 * Edits are in-memory only — the editor's row state is not yet wired back to the Files API.
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

  // Prefer the first Parquet file (the typical primary output), else the first data file.
  const defaultPath = useMemo(() => {
    const firstParquet = dataFiles.find((file) => formatFromFileName(file.path) === 'parquet');
    return firstParquet?.path ?? dataFiles[0]?.path ?? null;
  }, [dataFiles]);

  // Default once files resolve; keep the current pick if it survives.
  useEffect(() => {
    setSelectedPath((prev) =>
      prev && dataFiles.some((file) => file.path === prev) ? prev : defaultPath
    );
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

  const isResolving = isResultsLoading || isFilesLoading;

  const fileSelector =
    dataFiles.length > 1 ? (
      <Flex align="center" gap="density-sm" className="shrink-0">
        <Text kind="label/semibold/sm" className="text-secondary">
          File
        </Text>
        <SelectRoot
          value={selectedPath ?? undefined}
          onValueChange={(value: string) => setSelectedPath(value)}
        >
          <SelectTrigger
            placeholder="Select a file"
            // Trigger normally shows the raw value (full path); render the basename to match
            // the list items, and truncate with a leading ellipsis so the extension stays visible.
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
      return <Empty title="Could not parse file" description={parsed.error} />;
    }

    return (
      <FileRowEditor
        key={selectedPath}
        fileName={selectedPath ?? undefined}
        fileSizeLabel={selectedFile ? getHumanReadableFileSize(selectedFile.size) : undefined}
        initialRows={parsed.rows}
        showOpenFile={false}
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
