// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Panel, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { ResultsPreviewTable } from '@studio/routes/AnonymizerJobDetailRoute/components/ResultsPreviewTable';
import { useResultPreview } from '@studio/routes/AnonymizerJobDetailRoute/useResultPreview';
import type { FC } from 'react';

interface ResultsPreviewPanelProps {
  readonly workspace: string;
  readonly artifactUrl: string | undefined;
}

export const ResultsPreviewPanel: FC<ResultsPreviewPanelProps> = ({ workspace, artifactUrl }) => {
  const { rows, columns, isLoading, error } = useResultPreview(workspace, artifactUrl);

  return (
    <Panel slotHeading="Preview" elevation="high" density="compact">
      {error ? (
        <Banner kind="inline" status="error">
          Could not load the result preview.
        </Banner>
      ) : isLoading ? (
        <Spinner aria-label="Loading preview" />
      ) : rows.length ? (
        <Stack gap="density-md">
          <ResultsPreviewTable rows={rows} columns={columns} />
          <Text kind="body/regular/sm">
            Showing the first {rows.length} records. Download the result for the full dataset.
          </Text>
        </Stack>
      ) : (
        <Text kind="body/regular/md">No preview available for this job.</Text>
      )}
    </Panel>
  );
};
