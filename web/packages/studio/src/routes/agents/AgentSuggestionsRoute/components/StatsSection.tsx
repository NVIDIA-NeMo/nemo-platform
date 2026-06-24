// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Flex, Grid, Stack, Text } from '@nvidia/foundations-react-core';
import { SeverityStat } from '@studio/routes/agents/AgentSuggestionsRoute/components/SeverityStat';
import { StatColumn } from '@studio/routes/agents/AgentSuggestionsRoute/components/StatColumn';
import type { FC } from 'react';

interface SeverityCounts {
  high: number;
  low: number;
}

interface StatsSectionProps {
  stats: { agentCount: number; modelCount: number } & SeverityCounts;
  previousStats: SeverityCounts;
  hasPreviousRun: boolean;
}

export const StatsSection: FC<StatsSectionProps> = ({ stats, previousStats, hasPreviousRun }) => (
  <Grid cols={{ md: 1, lg: hasPreviousRun ? 3 : 2 }} gap="density-md">
    <Card>
      <Flex gap="density-2xl">
        <StatColumn label="Agents" value={stats.agentCount} />
        <StatColumn label="Models" value={stats.modelCount} />
      </Flex>
    </Card>
    <Card>
      <Stack gap="density-xxs">
        <Text kind="title/xs" color="secondary">
          Suggestions
        </Text>
        <Flex gap="density-2xl" align="center">
          <SeverityStat value={stats.high} label="HIGH" />
          <SeverityStat value={stats.low} label="LOW" />
        </Flex>
      </Stack>
    </Card>
    {hasPreviousRun && (
      <Card>
        <Stack gap="density-xxs">
          <Text kind="title/xs" color="secondary">
            Previous run
          </Text>
          <Flex gap="density-2xl" align="center">
            <SeverityStat value={previousStats.high} label="HIGH" />
            <SeverityStat value={previousStats.low} label="LOW" />
          </Flex>
        </Stack>
      </Card>
    )}
  </Grid>
);
