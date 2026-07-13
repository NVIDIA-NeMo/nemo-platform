// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { Flex, Grid, ProgressBar, Skeleton, Stack, Text } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import { ColumnProfileCard } from '@studio/routes/DataDesignerJobDetailsRoute/ColumnProfileCard';
import {
  formatPercent,
  getPercentComplete,
} from '@studio/routes/DataDesignerJobDetailsRoute/datasetProfilerTypes';
import { useDataDesignerJobAnalysis } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerJobAnalysis';
import { useDataDesignerJobFromRoute } from '@studio/routes/DataDesignerJobDetailsRoute/useDataDesignerJobFromRoute';
import type { FC } from 'react';

const ColumnGrid: FC<{ children: React.ReactNode }> = ({ children }) => (
  <Grid cols={{ xs: 1, sm: 2, xl: 3 }} gap="density-lg">
    {children}
  </Grid>
);

export const DatasetProfilerSection: FC = () => {
  const { workspace, jobName, job } = useDataDesignerJobFromRoute();

  const isTerminal = job?.status != null && PlatformJobTerminalStatuses.includes(job.status);

  const { analysis, hasAnalysis, isLoading, isError } = useDataDesignerJobAnalysis(
    workspace,
    jobName,
    { enabled: isTerminal }
  );

  // Job still running: the profiler hasn't produced an analysis result yet.
  if (!isTerminal) {
    return <Empty title="The dataset profile will appear here once the job completes." />;
  }

  if (isError) {
    return (
      <Empty
        title="Failed to load dataset profile"
        description="The profiler analysis could not be loaded for this job."
      />
    );
  }

  if (isLoading && !analysis) {
    return (
      <ColumnGrid>
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-lg" />
        ))}
      </ColumnGrid>
    );
  }

  if (!hasAnalysis) {
    return <Empty title="No dataset profile was generated for this job." />;
  }

  const columns = analysis?.column_statistics ?? [];
  const percentComplete = analysis ? getPercentComplete(analysis) : 0;

  return (
    <Stack gap="density-2xl" className="w-full">
      {analysis ? (
        <Stack gap="2">
          <Flex justify="between" align="center" className="flex-wrap" gap="density-md">
            <Text kind="body/regular/md">
              {analysis.num_records.toLocaleString()} of{' '}
              {analysis.target_num_records.toLocaleString()} rows
            </Text>
            <Text kind="body/regular/sm" className="text-muted">
              {formatPercent(percentComplete)} complete
            </Text>
          </Flex>
          <ProgressBar
            kind="determinate"
            value={percentComplete}
            aria-label="Dataset completeness"
          />
        </Stack>
      ) : null}

      {columns.length > 0 ? (
        <ColumnGrid>
          {columns.map((stats) => (
            <ColumnProfileCard key={stats.column_name} stats={stats} />
          ))}
        </ColumnGrid>
      ) : (
        <Empty title="The profile did not include any column statistics." />
      )}
    </Stack>
  );
};
