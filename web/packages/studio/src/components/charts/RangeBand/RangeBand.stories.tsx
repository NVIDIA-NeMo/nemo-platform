// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { useRangeBand } from '@studio/components/charts/RangeBand';
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from 'recharts';

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));

const makeSeries = (steps: number[], start: number, end: number, noiseScale = 0, seed = 1) => {
  let rng = seed;
  const next = () => {
    rng = (rng * 1664525 + 1013904223) & 0xffffffff;
    return (rng >>> 0) / 0xffffffff;
  };
  return steps.map((step) => {
    const t = step / (steps[steps.length - 1] ?? 1);
    const base = start + (end - start) * sigmoid((t - 0.5) * 8);
    const noise = noiseScale > 0 ? (next() - 0.5) * 2 * noiseScale : 0;
    return { step, mean: Math.max(0, base + noise) };
  });
};

const STEPS = Array.from({ length: 51 }, (_, i) => i * 10);
const series = makeSeries(STEPS, 0.15, 0.65, 0.01, 7);

const chartData = series.map(({ step, mean }) => {
  const t = step / 500;
  const halfBand = 0.22 * (1 - t) ** 2 + 0.02;
  return { step, mean, lower: Math.max(0, mean - halfBand), upper: mean + halfBand };
});

interface DemoDataPoint {
  step: number;
  mean?: number;
  lower?: number;
  upper?: number;
}

function DemoTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const pt = payload[0]?.payload as DemoDataPoint | undefined;
  return (
    <div className="bg-component-tooltip border border-component-tooltip shadow-sm rounded-lg p-3 text-sm min-w-36">
      <p className="font-semibold mb-1">Step {label}</p>
      {pt?.mean !== undefined && (
        <p className="text-[var(--text-color-accent-green)]">Mean: {pt.mean.toFixed(4)}</p>
      )}
      {pt?.lower !== undefined && pt?.upper !== undefined && (
        <p className="text-[var(--text-color-accent-green)] opacity-70">
          Range: {pt.lower.toFixed(3)} – {pt.upper.toFixed(3)}
        </p>
      )}
    </div>
  );
}

interface DemoProps {
  showLine?: boolean;
  fill?: string;
  fillOpacity?: number;
  height?: number;
}

function RangeBandDemo({
  showLine = true,
  fill = 'var(--text-color-accent-green)',
  fillOpacity = 0.5,
  height = 300,
}: DemoProps) {
  const band = useRangeBand({
    lowerKey: 'lower',
    upperKey: 'upper',
    fill,
    fillOpacity,
    name: 'Range band (p25–p75)',
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
        <XAxis
          dataKey="step"
          type="number"
          domain={['dataMin', 'dataMax']}
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <YAxis tick={{ fontSize: 11 }} tickLine={false} tickCount={6} />
        <Tooltip
          content={<DemoTooltip />}
          cursor={{ stroke: 'rgba(255,255,255,0.2)', strokeWidth: 1 }}
        />
        <Legend iconType="square" wrapperStyle={{ paddingTop: 12 }} />

        {band}

        {showLine && (
          <Line
            type="monotone"
            dataKey="mean"
            stroke="var(--text-color-accent-green)"
            strokeWidth={2}
            dot={false}
            name="Mean"
            legendType="square"
            isAnimationActive={false}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

const meta: Meta<typeof RangeBandDemo> = {
  title: 'Charts/RangeBand',
  component: RangeBandDemo,
  parameters: {
    layout: 'padded',
    backgrounds: { default: 'dark' },
  },
};

export default meta;
type Story = StoryObj<typeof RangeBandDemo>;

export const WithLine: Story = {
  name: 'Band + mean line',
  args: { showLine: true, fill: 'var(--text-color-accent-green)', fillOpacity: 0.5, height: 300 },
};

export const BandOnly: Story = {
  name: 'Band only (no line)',
  args: { showLine: false, fill: 'var(--text-color-accent-green)', fillOpacity: 0.5, height: 300 },
};

export const CustomColor: Story = {
  name: 'Custom color (blue)',
  args: { showLine: true, fill: 'var(--text-color-accent-blue)', fillOpacity: 0.45, height: 300 },
};
