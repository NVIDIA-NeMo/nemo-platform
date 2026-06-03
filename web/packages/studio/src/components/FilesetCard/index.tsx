// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput, FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Stack } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { FilesetMetadataPanel } from '@studio/components/FilesetCard/FilesetMetadataPanel';
import { ReadmeBody } from '@studio/components/FilesetCard/ReadmeBody';
import { isRootReadme, parseReadme } from '@studio/components/FilesetCard/utils';
import { useMemo, type FC } from 'react';

export interface FilesetCardProps {
  workspace: string;
  filesetName: string;
  fileset: FilesetOutput;
  files: FilesetFileOutput[] | undefined;
  isFilesLoading: boolean;
  isFilesError: boolean;
  testId?: string;
  metadataPanelTestId?: string;
  noReadmeMessage?: string;
  filesErrorMessage?: string;
}

export const FilesetCard: FC<FilesetCardProps> = ({
  workspace,
  filesetName,
  fileset,
  files,
  isFilesLoading,
  isFilesError,
  testId,
  metadataPanelTestId,
  noReadmeMessage,
  filesErrorMessage,
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

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col gap-density-xl md:flex-row md:items-stretch"
      data-testid={testId}
    >
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-lg border border-base bg-surface-raised p-density-xl md:flex-2">
        <Stack gap="density-md">
          <ReadmeBody
            isFilesError={isFilesError}
            isFilesLoading={isFilesLoading}
            readmePath={readmePath}
            isContentLoading={isContentLoading}
            isContentError={isContentError}
            content={parsed?.content}
            noReadmeMessage={noReadmeMessage}
            filesErrorMessage={filesErrorMessage}
          />
        </Stack>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto md:flex-1">
        <FilesetMetadataPanel
          fileset={fileset}
          readmeMetadata={parsed?.metadata}
          testId={metadataPanelTestId}
        />
      </div>
    </div>
  );
};
