// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput, FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Grid, GridItem, Stack, Text } from '@nvidia/foundations-react-core';
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
    <Grid
      cols={{ base: 1, xl: 12 }}
      gap="density-xl"
      className="w-full items-start"
      data-testid={testId}
    >
      <GridItem
        cols={{ lg: 8 }}
        className="min-w-0 overflow-hidden rounded-lg border border-base bg-surface-raised p-density-xl"
      >
        <Stack gap="density-md">
          {fileset.description && (
            <Text kind="body/regular/md" data-testid={testId ? `${testId}-description` : undefined}>
              {fileset.description}
            </Text>
          )}
          <ReadmeBody
            isFilesError={isFilesError}
            readmePath={readmePath}
            isContentLoading={isContentLoading}
            isContentError={isContentError}
            content={parsed?.content}
            noReadmeMessage={noReadmeMessage}
            filesErrorMessage={filesErrorMessage}
          />
        </Stack>
      </GridItem>
      <GridItem cols={{ lg: 4 }} className="min-w-0">
        <FilesetMetadataPanel
          fileset={fileset}
          readmeMetadata={parsed?.metadata}
          testId={metadataPanelTestId}
        />
      </GridItem>
    </Grid>
  );
};
