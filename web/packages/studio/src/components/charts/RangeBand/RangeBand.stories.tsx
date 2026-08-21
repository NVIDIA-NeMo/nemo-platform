// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { RangeBand } from '@studio/components/charts/RangeBand';
import type { RangeBandSeries } from '@studio/components/charts/RangeBand/types';

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));

const makeMean = (steps: number[], start: number, end: number, noiseScale = 0, seed = 1) => {
  let rng = seed;
  const next = () => {
    rng = (rng * 1664525 + 1013904223) & 0xffffffff;
    return (rng >>> 0) / 0xffffffff;
  };
  return steps.map((step) => {
    const t = step / (steps[steps.length - 1] ?? 1);
    const base = start + (end - start) * sigmoid((t - 0.5) * 8);
    const noise = noiseScale > 0 ? (next() - 0.5) * 2 * noiseScale : 0;
    return Math.max(0, base + noise);
  });
};

const STEPS = Array.from({ length: 51 }, (_, i) => i * 10);

/** The spread narrows as training converges, which is what makes the band worth drawing. */
const bandAround = (mean: number[], width: number, floor = 0.02) => {
  const half = STEPS.map((step) => width * (1 - step / 500) ** 2 + floor);
  return {
    lower: mean.map((value, index) => Math.max(0, value - half[index])),
    upper: mean.map((value, index) => value + half[index]),
  };
};

const candidateMean = makeMean(STEPS, 0.15, 0.65, 0.01, 7);
const candidate: RangeBandSeries = {
  id: 'candidate',
  label: 'Candidate',
  data: candidateMean,
  ...bandAround(candidateMean, 0.08),
};

const baselineMean = makeMean(STEPS, 0.12, 0.48, 0.008, 23);
const baseline: RangeBandSeries = {
  id: 'baseline',
  label: 'Baseline',
  data: baselineMean,
  dashed: true,
  ...bandAround(baselineMean, 0.05),
};

const LAST_STEP = STEPS.length - 1;

/**
 * A right-skewed spread: the long upper tail pins the p50 to the band's floor early, then the tail
 * collapses and the floor falls away, leaving the same line near the ceiling.
 */
const latencyP50 = STEPS.map((step) => 140 - 40 * (step / 500) + 9 * Math.sin(step / 55));
const latency: RangeBandSeries = {
  id: 'latency',
  label: 'p50 (p10–p90 band)',
  data: latencyP50,
  lower: latencyP50.map((value, index) => value - 18 - 55 * (index / LAST_STEP)),
  upper: latencyP50.map((value, index) => value + 12 + 145 * (1 - index / LAST_STEP)),
};

const meta: Meta<typeof RangeBand> = {
  title: 'Charts/RangeBand',
  component: RangeBand,
  parameters: {
    layout: 'padded',
    backgrounds: { default: 'dark' },
  },
  args: {
    series: [candidate],
    xAxis: STEPS,
    xAxisLabel: 'Step',
    yAxisLabel: 'Accuracy',
    title: 'Training accuracy',
  },
};

export default meta;
type Story = StoryObj<typeof RangeBand>;

export const Default: Story = {
  name: 'Band + mean line',
};

export const BandOnly: Story = {
  name: 'Band only (no line)',
  args: {
    series: [
      { id: candidate.id, label: 'p25–p75', lower: candidate.lower, upper: candidate.upper },
    ],
  },
};

export const OffCenterLine: Story = {
  name: 'Line off-center in the band',
  args: {
    series: [latency],
    title: 'Request latency',
    yAxisLabel: 'ms',
    bandOpacity: 0.35,
  },
};

export const MultipleSeries: Story = {
  name: 'Two series',
  args: { series: [baseline, candidate] },
};

export const LegendBottom: Story = {
  name: 'Legend below the plot',
  args: { series: [baseline, candidate], legendPosition: 'bottom', title: undefined },
};

export const FaintBands: Story = {
  name: 'Faint bands',
  args: { series: [baseline, candidate], bandOpacity: 0.15 },
};

export const Loading: Story = {
  args: { loading: true },
};

export const Empty: Story = {
  args: {
    series: [{ id: 'candidate', label: 'Candidate', lower: [], upper: [] }],
    emptyMessage: 'No runs yet',
  },
};
