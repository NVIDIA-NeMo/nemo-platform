// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChartXValue } from '@nemo/common/src/components/charts/types';
import { ComparisonLineChart } from '@nemo/common/src/components/ComparisonLineChart/index';
import type { ComparisonSeries } from '@nemo/common/src/components/ComparisonLineChart/types';
import { Card, Stack, Text } from '@nvidia/foundations-react-core';
import type {
  TraceStatisticsBucket,
  TraceStatisticsRange,
} from '@studio/components/AgentTraceStatistics/types';
import {
  bucketAdverbForRange,
  formatBucketTick,
  formatLatencyMs,
  formatTokens,
} from '@studio/components/AgentTraceStatistics/utils';
import { formatCost } from '@studio/util/intakeTelemetry';
import { type FC, useMemo } from 'react';

interface Props {
  buckets: TraceStatisticsBucket[];
  range: TraceStatisticsRange;
  isPending?: boolean;
  height?: number;
}

interface SeriesSpec {
  id: string;
  label: string;
  color: string;
  select: (bucket: TraceStatisticsBucket) => number | null;
  format: (value: number) => string;
}

const SERIES: SeriesSpec[] = [
  {
    id: 'cost',
    label: 'Cost',
    color: 'var(--text-color-accent-green)',
    select: (bucket) => bucket.costUsd,
    format: formatCost,
  },
  {
    id: 'tokens',
    label: 'Tokens',
    color: 'var(--text-color-accent-blue)',
    select: (bucket) => bucket.tokens,
    format: formatTokens,
  },
  {
    id: 'latency',
    label: 'Latency',
    color: 'var(--text-color-accent-yellow-strong)',
    select: (bucket) => bucket.latencyMs,
    format: formatLatencyMs,
  },
];

const DEFAULT_HEIGHT = 320;

const asDate = (value: ChartXValue): Date =>
  value instanceof Date ? value : new Date(value as number);

export const TraceStatisticsChart: FC<Props> = ({
  buckets,
  range,
  isPending,
  height = DEFAULT_HEIGHT,
}) => {
  const xAxis = useMemo(() => buckets.map((bucket) => new Date(bucket.timestamp)), [buckets]);

  const series = useMemo<ComparisonSeries[]>(
    () =>
      SERIES.map((spec) => ({
        id: spec.id,
        label: spec.label,
        color: spec.color,
        data: buckets.map(spec.select),
        valueFormatter: (value: number | null) => (value == null ? '—' : spec.format(value)),
      })),
    [buckets]
  );

  const formatXValue = (value: ChartXValue): string =>
    formatBucketTick(asDate(value).getTime(), range);

  return (
    <Card>
      <Stack padding="density-xl">
        <ComparisonLineChart
          title={<Text kind="title/sm">{`${bucketAdverbForRange(range)} averages over time`}</Text>}
          series={series}
          xAxis={xAxis}
          height={height}
          loading={isPending}
          emptyMessage="No traces in this range"
          formatXValue={formatXValue}
          formatYValue={formatTokens}
        />
      </Stack>
    </Card>
  );
};
