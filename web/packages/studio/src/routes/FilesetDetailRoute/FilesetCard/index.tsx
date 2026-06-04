// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FilesetPurpose,
  type FilesetFileOutput,
  type FilesetOutput,
} from '@nemo/sdk/generated/platform/schema';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { ResizeablePanel } from '@studio/components/common/ResizeablePanel';
import { DatasetSamplePanel } from '@studio/routes/FilesetDetailRoute/FilesetCard/DatasetSamplePanel';
import { ReadmeBody } from '@studio/routes/FilesetDetailRoute/FilesetCard/ReadmeBody';
import { FilesetMetadataPanel } from '@studio/routes/FilesetDetailRoute/FilesetMetadataPanel';
import { isRootReadme, parseReadme } from '@studio/routes/FilesetDetailRoute/utils';
import { useMemo, type FC } from 'react';

export interface FilesetCardProps {
  workspace: string;
  filesetName: string;
  fileset: FilesetOutput;
  files: FilesetFileOutput[] | undefined;
  isFilesError: boolean;
}

/**
 * Purpose-agnostic card for a fileset detail page: renders the root README as
 * markdown alongside a metadata panel. Used for every fileset purpose — the
 * panel's README-frontmatter "Details" section simply collapses when those
 * fields (license, tags, base model, …) aren't present.
 */
export const FilesetCard: FC<FilesetCardProps> = ({
  workspace,
  filesetName,
  fileset,
  files,
  isFilesError,
}) => {
  const readmePath = useMemo(() => files?.find(isRootReadme)?.path, [files]);

  const {
    data: rawContent,
    isLoading: isContentLoading,
    isError: isContentError,
  } = useDatasetFileContent({
    workspace,
    name: filesetName,
    path: readmePath ?? '',
    enabled: Boolean(readmePath),
  });

  const parsed = useMemo(
    () => (rawContent !== undefined ? parseReadme(rawContent) : undefined),
    [rawContent]
  );

  const isDataset = fileset.purpose === FilesetPurpose.dataset;

  return (
    <div className="h-[calc(100vh-12rem)] min-h-96 w-full" data-testid="fileset-card">
      <ResizeablePanel
        defaultLeftWidth={700}
        minLeftWidth={280}
        leftClassName="p-density-xl overflow-y-auto"
        rightClassName="overflow-y-auto"
        slotLeft={
          <Stack gap="density-md">
            {fileset.description && (
              <Text kind="body/regular/md" data-testid="fileset-card-description">
                {fileset.description}
              </Text>
            )}
            <ReadmeBody
              isFilesError={isFilesError}
              readmePath={readmePath}
              isContentLoading={isContentLoading}
              isContentError={isContentError}
              content={parsed?.content}
            />
          </Stack>
        }
        slotRight={
          <Stack gap="density-xl" className="h-full p-density-xl">
            <FilesetMetadataPanel fileset={fileset} readmeMetadata={parsed?.metadata} />
            {isDataset && (
              <DatasetSamplePanel workspace={workspace} filesetName={filesetName} files={files} />
            )}
          </Stack>
        }
      />
    </div>
  );
};
