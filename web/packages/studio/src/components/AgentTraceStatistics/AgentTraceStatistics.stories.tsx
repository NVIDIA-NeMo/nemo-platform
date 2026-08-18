// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import {
  AgentTraceStatistics,
  type AgentTraceStatisticsProps,
} from '@studio/components/AgentTraceStatistics/index';
import type {
  TraceStatisticsRange,
  TraceStatisticsSample,
} from '@studio/components/AgentTraceStatistics/types';
import { type FC, useState } from 'react';

const ANCHOR = new Date('2026-07-01T00:00:00Z').getTime();
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/** Deterministic LCG — fixtures must not change between story renders. */
const makeRandom = (seed: number): (() => number) => {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
};

interface FixtureOptions {
  buckets: number;
  bucketMs: number;
  tracesPerBucket?: number;
  seed?: number;
}

/**
 * Token counts swing on a slow sine so the chart shows the peaks and troughs of a real workload;
 * latency and cost are derived from tokens with independent jitter.
 */
const makeTraces = ({
  buckets,
  bucketMs,
  tracesPerBucket = 6,
  seed = 42,
}: FixtureOptions): TraceStatisticsSample[] => {
  const random = makeRandom(seed);
  const samples: TraceStatisticsSample[] = [];
  const start = ANCHOR - (buckets - 1) * bucketMs;

  for (let bucket = 0; bucket < buckets; bucket++) {
    const wave = Math.sin(bucket / 1.7) * 0.5 + Math.sin(bucket / 5.3) * 0.5;
    const baseTokens = 2200 + wave * 1300;
    for (let i = 0; i < tracesPerBucket; i++) {
      const totalTokens = Math.max(120, Math.round(baseTokens * (0.85 + random() * 0.3)));
      const msPerToken = 0.045 + random() * 0.02;
      samples.push({
        startedAt: new Date(start + bucket * bucketMs + random() * bucketMs),
        totalTokens,
        durationMs: Math.round(totalTokens * msPerToken * 1000) / 1000,
        costUsd: totalTokens * 0.0000032 * (0.9 + random() * 0.2),
      });
    }
  }
  return samples;
};

const MONTH_TRACES = makeTraces({ buckets: 31, bucketMs: DAY_MS });
const WEEK_TRACES = makeTraces({ buckets: 7, bucketMs: DAY_MS, seed: 7 });
const DAY_TRACES = makeTraces({ buckets: 24, bucketMs: HOUR_MS, tracesPerBucket: 3, seed: 11 });

const TRACES_BY_RANGE: Record<TraceStatisticsRange, TraceStatisticsSample[]> = {
  day: DAY_TRACES,
  week: WEEK_TRACES,
  month: MONTH_TRACES,
};

const meta: Meta<typeof AgentTraceStatistics> = {
  component: AgentTraceStatistics,
  title: 'Studio/AgentTraceStatistics',
  args: {
    range: 'month',
    traces: MONTH_TRACES,
    onRangeChange: () => {},
    onViewTraces: () => {},
  },
  argTypes: {
    range: { control: 'select', options: ['day', 'week', 'month'] },
    chartHeight: { control: { type: 'range', min: 160, max: 600, step: 20 } },
  },
  decorators: [
    (Story) => (
      <div className="w-full max-w-[1200px] p-6">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof AgentTraceStatistics>;

/** Stands in for the caller's refetch: changing the range swaps which fixture is passed in. */
const RangeAwareStatistics: FC<AgentTraceStatisticsProps> = (props) => {
  const [range, setRange] = useState<TraceStatisticsRange>(props.range);
  return (
    <AgentTraceStatistics
      {...props}
      range={range}
      traces={TRACES_BY_RANGE[range]}
      onRangeChange={setRange}
    />
  );
};

export const Default: Story = {
  render: (args) => <RangeAwareStatistics {...args} />,
};

/** Hourly buckets — the tick formatter switches from dates to hours. */
export const DayRange: Story = {
  args: { range: 'day', traces: DAY_TRACES },
};

export const Loading: Story = {
  args: { isPending: true, traces: [] },
};

/**
 * First run: the tiles and chart give way to instructions, since four zeros and a blank grid tell
 * the user nothing about how to get data.
 */
export const Empty: Story = {
  args: {
    traces: [],
    onRunAgent: () => {},
    onLearnMore: () => {},
  },
};

/** Traces missing cost or token rollups still contribute what they have. */
export const PartialRollups: Story = {
  args: {
    traces: MONTH_TRACES.map((trace, index) =>
      index % 3 === 0 ? { ...trace, costUsd: null, totalTokens: null } : trace
    ),
  },
};

/** No `onViewTraces` hides the action — for surfaces that are already the traces list. */
export const WithoutViewTracesAction: Story = {
  args: { onViewTraces: undefined },
};
