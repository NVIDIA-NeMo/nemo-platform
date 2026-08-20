// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatNumericValue } from '@nemo/common/src/components/charts/format';
import { ComparisonLineChart } from '@nemo/common/src/components/ComparisonLineChart/index';
import type { ComparisonSeries } from '@nemo/common/src/components/ComparisonLineChart/types';
import type { Meta, StoryObj } from '@storybook/react';

const STEPS = ['Step 1', 'Step 2', 'Step 3', 'Step 4', 'Step 5', 'Step 6'];

const ACCURACY_SERIES: ComparisonSeries[] = [
  { id: 'baseline', label: 'Baseline', data: [0.41, 0.44, 0.46, 0.47, 0.47, 0.48] },
  { id: 'candidate', label: 'Candidate v2', data: [0.39, 0.48, 0.57, 0.63, 0.68, 0.71] },
];

const percent = (value: number) => `${(value * 100).toFixed(0)}%`;

const meta: Meta<typeof ComparisonLineChart> = {
  component: ComparisonLineChart,
  title: 'Studio Common/ComparisonLineChart',
  args: {
    series: ACCURACY_SERIES,
    xAxis: STEPS,
    yAxisLabel: 'Accuracy',
    formatYValue: percent,
  },
  argTypes: {
    curve: { control: 'select', options: ['linear', 'monotone', 'step', 'natural'] },
    xAxisType: { control: 'select', options: ['category', 'number', 'time'] },
    height: { control: { type: 'range', min: 160, max: 600, step: 20 } },
  },
  decorators: [
    (Story) => (
      <div className="p-4 w-[720px] max-w-full">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ComparisonLineChart>;

export const Default: Story = {};

/** Click a legend entry to hide a run; hover one to fade the others. */
export const ManySeries: Story = {
  args: {
    series: [
      { id: 'run-a', label: 'gpt-oss-120b', data: [0.41, 0.5, 0.56, 0.6, 0.63, 0.65] },
      { id: 'run-b', label: 'nemotron-super', data: [0.38, 0.47, 0.58, 0.66, 0.71, 0.74] },
      { id: 'run-c', label: 'llama-3.3-70b', data: [0.44, 0.49, 0.52, 0.55, 0.57, 0.58] },
      { id: 'run-d', label: 'qwen3-32b', data: [0.35, 0.42, 0.5, 0.54, 0.59, 0.62] },
      { id: 'run-e', label: 'mistral-small', data: [0.3, 0.36, 0.41, 0.45, 0.48, 0.5] },
    ],
  },
};

/** `dashed` marks the reference run; `referenceLines` marks the ship threshold. */
export const BaselineAndTarget: Story = {
  args: {
    series: [{ ...ACCURACY_SERIES[0], dashed: true }, ACCURACY_SERIES[1]],
    referenceLines: [{ y: 0.7, label: 'Ship target' }],
    yAxisMin: 0,
    yAxisMax: 1,
  },
};

/** `Date` x values switch the axis to time scaling automatically. */
export const TimeAxis: Story = {
  args: {
    xAxis: [
      new Date('2026-08-01T09:00:00Z'),
      new Date('2026-08-01T12:00:00Z'),
      new Date('2026-08-02T09:00:00Z'),
      new Date('2026-08-04T09:00:00Z'),
      new Date('2026-08-07T09:00:00Z'),
      new Date('2026-08-11T09:00:00Z'),
    ],
    xAxisLabel: 'Run started',
  },
};

/** A numeric axis with per-series value formatting for mixed units. */
export const NumericAxis: Story = {
  args: {
    xAxis: [1, 2, 4, 8, 16, 32],
    xAxisLabel: 'Concurrency',
    yAxisLabel: 'Latency',
    formatYValue: (value: number) => `${value.toFixed(0)}ms`,
    series: [
      { id: 'p50', label: 'p50', data: [420, 435, 470, 560, 790, 1400] },
      { id: 'p95', label: 'p95', data: [810, 860, 950, 1180, 1760, 3200] },
    ],
  },
};

/** `null` values break the line rather than interpolating across a missing run. */
export const WithGaps: Story = {
  args: {
    series: [
      { id: 'baseline', label: 'Baseline', data: [0.41, 0.44, null, 0.47, 0.47, 0.48] },
      { id: 'candidate', label: 'Candidate v2', data: [0.39, null, null, 0.63, 0.68, 0.71] },
    ],
    showMarks: true,
  },
};

export const SeriesHiddenByDefault: Story = {
  args: { initialHiddenSeriesIds: ['baseline'] },
};

export const StaticLegend: Story = {
  args: { legendInteractive: false },
};

/** Title on the left, legend on the right — the default header layout. */
export const WithTitle: Story = {
  args: {
    title: 'Daily averages over time',
    xAxis: ['7/1', '7/7', '7/13', '7/19', '7/25', '7/31'],
    yAxisLabel: undefined,
    formatYValue: formatNumericValue,
    series: [
      { id: 'cost', label: 'Cost', data: [12, 14, 11, 15, 13, 12] },
      { id: 'tokens', label: 'Tokens', data: [2980, 2380, 3810, 1650, 3520, 2210] },
      { id: 'latency', label: 'Latency', data: [210, 240, 190, 260, 230, 250] },
    ],
  },
};

/** Legend below the plot, centered — the layout to use when the header row is already busy. */
export const LegendBelow: Story = {
  args: { legendPosition: 'bottom' },
};

export const Loading: Story = {
  args: { loading: true },
};

/** The frame, axis labels, and legend stay put so the chart doesn't collapse while it waits for data. */
export const Empty: Story = {
  args: {
    series: [
      { id: 'baseline', label: 'Baseline', data: [] },
      { id: 'candidate', label: 'Candidate v2', data: [] },
    ],
    xAxis: [],
    xAxisLabel: 'Step',
    emptyMessage: 'No runs to compare yet',
  },
};

/** An annotation between two series, with the multiplier computed from the data. */
export const WithAnnotation: Story = {
  args: {
    series: [{ ...ACCURACY_SERIES[0], dashed: true }, ACCURACY_SERIES[1]],
    yAxisMin: 0,
    yAxisMax: 1,
    annotations: [
      {
        x: 'Step 6',
        betweenSeriesIds: ['baseline', 'candidate'],
        description: 'Higher accuracy',
      },
    ],
  },
};

/**
 * Shared x grid for the platform-comparison stories below. Each platform only covers part of the
 * interactivity range, so values outside its range are `null` — leading and trailing nulls shorten
 * a line without breaking it.
 */
const INTERACTIVITY = [
  20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200,
];

const onInteractivityGrid = (points: Record<number, number>): (number | null)[] =>
  INTERACTIVITY.map((x) => points[x] ?? null);

const PLATFORM_COLORS = {
  gb300: 'var(--text-color-accent-yellow)',
  h200: 'var(--text-color-accent-green)',
  competition: 'var(--text-color-accent-gray)',
} as const;

/** Throughput-per-watt curves, where each platform is measured over a different interactivity band. */
export const TokensPerWattByInteractivity: Story = {
  args: {
    xAxis: INTERACTIVITY,
    xAxisLabel: 'Interactivity (TPS/User)',
    yAxisLabel: 'Tokens per watt',
    formatYValue: formatNumericValue,
    curve: 'linear',
    showMarks: true,
    yAxisMin: 0,
    height: 380,
    annotations: [
      {
        x: 120,
        betweenSeriesIds: ['h200', 'gb300'],
        label: '50X',
        description: 'Higher perf / watt',
      },
    ],
    series: [
      {
        id: 'gb300',
        label: 'GB300 NVL72',
        color: PLATFORM_COLORS.gb300,
        data: onInteractivityGrid({
          20: 8_300_000,
          30: 7_550_000,
          40: 6_800_000,
          50: 6_300_000,
          60: 5_900_000,
          70: 5_500_000,
          80: 4_900_000,
          90: 4_300_000,
          100: 3_700_000,
          110: 3_100_000,
          120: 2_550_000,
          130: 2_050_000,
          140: 1_600_000,
          150: 1_150_000,
          160: 800_000,
          170: 550_000,
          180: 350_000,
          190: 200_000,
          200: 120_000,
        }),
      },
      {
        id: 'h200',
        label: 'H200 NVL8',
        color: PLATFORM_COLORS.h200,
        data: onInteractivityGrid({
          30: 1_250_000,
          40: 700_000,
          50: 480_000,
          60: 330_000,
          70: 240_000,
          80: 175_000,
          90: 130_000,
          100: 95_000,
          110: 70_000,
          120: 55_000,
        }),
      },
      {
        id: 'competition',
        label: 'Competition',
        color: PLATFORM_COLORS.competition,
        dashed: true,
        data: onInteractivityGrid({
          80: 500_000,
          90: 420_000,
          100: 350_000,
          110: 300_000,
          120: 240_000,
          130: 180_000,
          140: 120_000,
          150: 90_000,
          160: 70_000,
          170: 50_000,
          180: 35_000,
          190: 25_000,
          200: 20_000,
        }),
      },
    ],
  },
};

/** The same comparison inverted: cost per token, where lower and flatter wins. */
export const TokenCostByInteractivity: Story = {
  args: {
    xAxis: INTERACTIVITY,
    xAxisLabel: 'Interactivity (TPS/User)',
    yAxisLabel: 'Cost per 1M tokens',
    formatYValue: (value: number) => `$${value.toFixed(2)}`,
    curve: 'linear',
    showMarks: true,
    annotations: [
      { x: 120, betweenSeriesIds: ['h200', 'gb300'], label: '35X', description: 'Lower cost' },
    ],
    yAxisMin: 0,
    yAxisMax: 5,
    height: 380,
    series: [
      {
        id: 'gb300',
        label: 'GB300 NVL72',
        color: PLATFORM_COLORS.gb300,
        data: onInteractivityGrid({
          20: 0.02,
          30: 0.02,
          40: 0.03,
          50: 0.03,
          60: 0.04,
          70: 0.04,
          80: 0.05,
          90: 0.05,
          100: 0.06,
          110: 0.07,
          120: 0.08,
          130: 0.1,
          140: 0.13,
          150: 0.17,
          160: 0.3,
          170: 0.55,
          180: 0.85,
          190: 1.15,
          200: 1.45,
        }),
      },
      {
        id: 'h200',
        label: 'H200 NVL8',
        color: PLATFORM_COLORS.h200,
        data: onInteractivityGrid({
          20: 0.02,
          30: 0.08,
          40: 0.25,
          50: 0.45,
          60: 0.72,
          70: 0.95,
          80: 1.5,
          90: 2.5,
          100: 3.3,
          110: 3.9,
          120: 4.15,
        }),
      },
      {
        id: 'competition',
        label: 'Competition',
        color: PLATFORM_COLORS.competition,
        dashed: true,
        data: onInteractivityGrid({
          70: 0.18,
          80: 0.2,
          90: 0.25,
          100: 0.3,
          110: 0.4,
          120: 0.48,
          130: 1.05,
          140: 2.1,
          150: 2.85,
          160: 3.65,
        }),
      },
    ],
  },
};
