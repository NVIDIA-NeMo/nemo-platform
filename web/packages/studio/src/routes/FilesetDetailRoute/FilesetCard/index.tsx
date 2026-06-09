// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FilesetPurpose,
  type FilesetFileOutput,
  type FilesetOutput,
} from '@nemo/sdk/generated/platform/schema';
import { Stack } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
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
    <div
      className="grid w-full grid-cols-1 gap-density-xl pt-density-xl lg:grid-cols-3"
      data-testid="fileset-card"
    >
      <div className="lg:col-span-2">
        <Stack gap="density-md">
          <ReadmeBody
            isFilesError={isFilesError}
            readmePath={readmePath}
            isContentLoading={isContentLoading}
            isContentError={isContentError}
            content={parsed?.content}
          />
        </Stack>
      </div>
      <div className="lg:col-span-1">
        <Stack gap="density-xl" className="h-full overflow-auto">
          <FilesetMetadataPanel fileset={fileset} readmeMetadata={parsed?.metadata} />
          {isDataset && (
            <DatasetSamplePanel workspace={workspace} filesetName={filesetName} files={files} />
          )}
        </Stack>
      </div>
    </div>
  );
};
