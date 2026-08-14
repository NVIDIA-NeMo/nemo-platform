// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StatTile, type StatTileProps } from '@nemo/common/src/components/StatTile/index';
import { Grid, Panel, Skeleton, Stack } from '@nvidia/foundations-react-core';
import type { TraceStatisticsSummary } from '@studio/components/AgentTraceStatistics/types';
import {
  formatCostUsd,
  formatMsPerToken,
  formatTokens,
} from '@studio/components/AgentTraceStatistics/utils';
import { type FC } from 'react';

interface Props {
  summary: TraceStatisticsSummary;
  isPending?: boolean;
}

export const TraceStatisticsTiles: FC<Props> = ({ summary, isPending }) => {
  const tiles: StatTileProps[] = [
    { label: 'Total traces', value: formatTokens(summary.totalTraces) },
    {
      label: 'Avg latency',
      value: formatMsPerToken(summary.avgLatencyMsPerToken),
      hint: 'ms/tok',
    },
    {
      label: 'Avg token count',
      value: formatTokens(summary.avgTokensPerRun),
      hint: 'per run',
    },
    { label: 'Avg cost', value: formatCostUsd(summary.avgCostUsd) },
  ];

  return (
    <Grid cols={{ base: 1, md: 2, lg: 4 }} gap="density-lg">
      {tiles.map((tile) =>
        isPending ? (
          <Panel key={tile.label} className="max-w-sm bg-surface-raised">
            <Stack gap="density-sm">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-20" />
            </Stack>
          </Panel>
        ) : (
          <StatTile key={tile.label} {...tile} className="bg-surface-raised" />
        )
      )}
    </Grid>
  );
};
