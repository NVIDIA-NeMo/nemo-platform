// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput, FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Grid, GridItem, Stack, Text } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { ReadmeBody } from '@studio/routes/ModelDetailRoute/ModelCardTab/ReadmeBody';
import { ModelMetadataPanel } from '@studio/routes/ModelDetailRoute/ModelMetadataPanel';
import { isRootReadme, parseReadme } from '@studio/routes/ModelDetailRoute/utils';
import { useMemo, type FC } from 'react';

export interface ModelCardTabProps {
  workspace: string;
  modelName: string;
  fileset: FilesetOutput;
  files: FilesetFileOutput[] | undefined;
  isFilesError: boolean;
}

export const ModelCardTab: FC<ModelCardTabProps> = ({
  workspace,
  modelName,
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
    name: modelName,
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
      data-testid="model-card-tab"
    >
      <GridItem
        cols={{ lg: 8 }}
        className="min-w-0 overflow-hidden rounded-lg border border-base bg-surface-raised p-density-xl"
      >
        <Stack gap="density-md">
          {fileset.description && (
            <Text kind="body/regular/md" data-testid="model-card-fileset-description">
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
      </GridItem>
      <GridItem cols={{ lg: 4 }} className="min-w-0">
        <ModelMetadataPanel fileset={fileset} readmeMetadata={parsed?.metadata} />
      </GridItem>
    </Grid>
  );
};
