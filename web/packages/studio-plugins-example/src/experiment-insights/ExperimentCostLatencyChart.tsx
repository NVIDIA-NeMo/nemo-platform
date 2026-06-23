// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Stack, Text } from '@nvidia/foundations-react-core';
import {
  toCostLatencyPoints,
  type CostLatencyPoint,
} from '@nemo/studio-plugins-example/experiment-insights/costLatency';
import type { SlotContextMap } from '@studio/plugins/types';
import { type FC, useMemo } from 'react';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';

type Props = SlotContextMap['experiments.group.afterSearch'];

const AXIS_STYLE = { fontSize: 11, fill: 'var(--text-color-base)' } as const;
const AXIS_LABEL_STYLE = { fill: 'var(--text-color-base)', fontSize: 12 } as const;

/**
 * Demo plugin surface: a scatter plot of mean cost vs. mean latency, one point per experiment in
 * the table view. Renders nothing when no experiment in view reports both metrics.
 */
export const ExperimentCostLatencyChart: FC<Props> = ({ experiments, experimentGroupName }) => {
  const points = useMemo(() => toCostLatencyPoints(experiments), [experiments]);

  if (points.length === 0) return null;

  return (
    <Card>
      <Stack gap="density-md" padding="density-xl">
        <Stack gap="density-xs">
          <Text kind="title/sm">Cost vs. latency</Text>
          <Text kind="body/regular/sm" color="secondary">
            Mean cost and latency per experiment in {experimentGroupName} ({points.length} plotted)
          </Text>
        </Stack>
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ top: 8, right: 24, bottom: 28, left: 8 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--border-color-base)"
              strokeOpacity={0.5}
            />
            <XAxis
              type="number"
              dataKey="cost"
              name="Cost"
              tick={AXIS_STYLE}
              tickFormatter={(value: number) => `$${value.toFixed(3)}`}
              label={{
                value: 'Avg cost (USD)',
                position: 'insideBottom',
                offset: -16,
                ...AXIS_LABEL_STYLE,
              }}
            />
            <YAxis
              type="number"
              dataKey="latency"
              name="Latency"
              width={64}
              tick={AXIS_STYLE}
              tickFormatter={(value: number) => `${Math.round(value)} ms`}
              label={{
                value: 'Avg latency (ms)',
                angle: -90,
                position: 'insideLeft',
                ...AXIS_LABEL_STYLE,
              }}
            />
            {/* Constant point size; ZAxis is required for Scatter to size its symbols. */}
            <ZAxis range={[80, 80]} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<CostLatencyTooltip />} />
            <Scatter data={points} fill="var(--text-color-brand)" />
          </ScatterChart>
        </ResponsiveContainer>
      </Stack>
    </Card>
  );
};

const CostLatencyTooltip: FC<TooltipProps<number, string>> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as CostLatencyPoint | undefined;
  if (!point) return null;

  return (
    <Stack
      gap="1"
      className="bg-component-tooltip border border-component-tooltip shadow-sm rounded-lg p-3"
    >
      <Text kind="label/semibold/md">{point.name}</Text>
      <Text kind="body/regular/sm" color="secondary">
        ${point.cost.toFixed(3)} · {Math.round(point.latency)} ms
      </Text>
    </Stack>
  );
};
