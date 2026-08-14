// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Grid, Skeleton, Stack, Text } from '@nvidia/foundations-react-core';
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

interface Tile {
  label: string;
  value: string;
  hint?: string;
}

export const TraceStatisticsTiles: FC<Props> = ({ summary, isPending }) => {
  const tiles: Tile[] = [
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
      {tiles.map((tile) => (
        <Card key={tile.label}>
          <Stack gap="density-sm" padding="density-xl">
            <Text kind="body/regular/md">{tile.label}</Text>
            {isPending ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <Text kind="body/bold/3xl">{tile.value}</Text>
            )}
            <Text kind="body/regular/sm" className="text-secondary">
              {tile.hint ?? ' '}
            </Text>
          </Stack>
        </Card>
      ))}
    </Grid>
  );
};
