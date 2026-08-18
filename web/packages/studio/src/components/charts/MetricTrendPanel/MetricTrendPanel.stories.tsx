// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import {
  MetricTrendPanel,
  type MetricTrendPoint,
} from '@studio/components/charts/MetricTrendPanel';

/** Deterministic wobbly upward trend so the story renders the same every run. */
const makePoints = (start: number, step: number, count = 30): MetricTrendPoint[] =>
  Array.from({ length: count }, (_, i) => ({
    label: `Day ${i + 1}`,
    value: Number((start + i * step + (i % 3 === 0 ? -step : step) * 0.8).toFixed(1)),
  }));

const meta: Meta<typeof MetricTrendPanel> = {
  title: 'Charts/MetricTrendPanel',
  component: MetricTrendPanel,
  args: {
    title: 'Primary use cases',
    description:
      'Continuously evaluate every merge to main against the full Support-Bench v3 benchmark.',
    comparisonLabel: 'vs. 7 days ago',
    series: [
      { id: 'solved', label: 'Solved', value: 78.4, delta: 3.3, points: makePoints(62, 0.55) },
      {
        id: 'helpfulness',
        label: 'Helpfulness',
        value: 84.1,
        delta: 1.2,
        points: makePoints(74, 0.35),
      },
      { id: 'tool-use', label: 'Tool Use', value: 69.2, delta: -2.4, points: makePoints(78, -0.3) },
    ],
  },
  decorators: [
    (Story) => (
      <div className="max-w-4xl">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof MetricTrendPanel>;

export const Default: Story = {
  args: { onViewClick: () => {} },
};

export const SingleSeries: Story = {
  args: {
    series: [
      { id: 'solved', label: 'Solved', value: 78.4, delta: 3.3, points: makePoints(62, 0.55) },
    ],
  },
};

export const NegativeDelta: Story = {
  args: { selectedSeriesId: 'tool-use' },
};

export const ZeroDelta: Story = {
  args: {
    series: [{ id: 'solved', label: 'Solved', value: 78.4, delta: 0, points: makePoints(78.4, 0) }],
  },
};

export const ValueCaption: Story = {
  args: {
    comparisonLabel: undefined,
    valueLabel: 'Latest result',
    series: [{ id: 'solved', label: 'Solved', value: 78.4, points: makePoints(62, 0.55) }],
  },
};

export const Loading: Story = {
  args: { isPending: true },
};
