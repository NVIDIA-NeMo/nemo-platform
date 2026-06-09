// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DEFAULT_MAX_FILE_SAMPLE_ROWS,
  type FileSampleMethod,
} from '@nemo/common/src/utils/sampleTextLines';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { Flex, Select, Stack, Text } from '@nvidia/foundations-react-core';
import { FileSamplingMethodSelect } from '@studio/components/FileSamplingSnippet/FileSamplingMethodSelect';
import {
  FileSamplingSnippet,
  type FileSamplingDisplayMode,
} from '@studio/components/FileSamplingSnippet/FileSamplingSnippet';
import { useMemo, useState, type FC } from 'react';

const SAMPLE_ROW_CAP = 25;

const SUPPORTED_EXTENSIONS = new Set(['.csv', '.json', '.jsonl', '.parquet']);

const isSupportedDataFile = (path: string): boolean => {
  const lower = path.toLowerCase();
  return [...SUPPORTED_EXTENSIONS].some((ext) => lower.endsWith(ext));
};

/**
 * JSON-per-line files preview cleanly as a dynamic-column table; everything
 * else falls back to the raw code editor so any text file is still readable.
 */
const supportsTablePreview = (path: string): boolean => {
  const lower = path.toLowerCase();
  return lower.endsWith('.jsonl') || lower.endsWith('.json');
};

export interface DatasetSamplePanelProps {
  workspace: string;
  filesetName: string;
  files: FilesetFileOutput[] | undefined;
}

/**
 * "Data sample" panel for the Dataset Card. Lets the user pick any file in the
 * fileset and preview a head / tail / random sample of its rows. JSONL/JSON
 * files render as a table; other files fall back to the code editor. Renders
 * nothing when the fileset has no files at all.
 */
export const DatasetSamplePanel: FC<DatasetSamplePanelProps> = ({
  workspace,
  filesetName,
  files,
}) => {
  const availableFiles = useMemo(
    () => (files ?? []).slice().sort((a, b) => a.path.localeCompare(b.path)),
    [files]
  );

  const [selectedFilePath, setSelectedFilePath] = useState<string | undefined>(undefined);
  const [sampleMethod, setSampleMethod] = useState<FileSampleMethod>('head');
  const [maxRows, setMaxRows] = useState(DEFAULT_MAX_FILE_SAMPLE_ROWS);

  // Default to the first supported data file; fall back to first file if none
  // match, and re-validate whenever the file list changes (rename/delete).
  const activeFilePath = useMemo(() => {
    if (selectedFilePath && availableFiles.some((f) => f.path === selectedFilePath)) {
      return selectedFilePath;
    }
    return (availableFiles.find((f) => isSupportedDataFile(f.path)) ?? availableFiles[0])?.path;
  }, [selectedFilePath, availableFiles]);

  // Label options by full relative path, not just the basename: datasets often
  // repeat a filename across folders (train/data.jsonl, test/data.jsonl), and
  // identical labels make a selection look like a no-op even though it changed.
  const fileItems = useMemo(
    () => availableFiles.map((f) => ({ value: f.path, children: f.path })),
    [availableFiles]
  );

  if (!activeFilePath) {
    return null;
  }

  const displayMode: FileSamplingDisplayMode = supportsTablePreview(activeFilePath)
    ? 'table'
    : 'code';

  return (
    <Stack
      gap="density-md"
      className="rounded-lg border border-base bg-surface-raised p-density-xl"
      data-testid="dataset-sample-panel"
    >
      <Flex justify="between" align="center" gap="density-md" wrap="wrap">
        <Text kind="title/sm">Data sample</Text>
        <Flex gap="density-md" align="center" wrap="wrap">
          <Select
            multiple={false}
            items={fileItems}
            value={activeFilePath}
            onValueChange={(next) => setSelectedFilePath(next as string)}
            className="w-[220px] grow-0"
            aria-label="Sample file"
          />
          <FileSamplingMethodSelect
            value={sampleMethod}
            onValueChange={setSampleMethod}
            rowCountGroup={{
              value: maxRows,
              onValueChange: setMaxRows,
              maxRows: SAMPLE_ROW_CAP,
            }}
          />
        </Flex>
      </Flex>

      <FileSamplingSnippet
        workspace={workspace}
        filesetName={filesetName}
        filePath={activeFilePath}
        maxSampleRows={maxRows}
        sampleMethod={sampleMethod}
        onSampledContentChange={NOOP_ON_SAMPLED_CONTENT_CHANGE}
        displayMode={displayMode}
      />
    </Stack>
  );
};

/** The panel only previews; it does not lift the sampled text to a parent. */
const NOOP_ON_SAMPLED_CONTENT_CHANGE = (): void => {};
