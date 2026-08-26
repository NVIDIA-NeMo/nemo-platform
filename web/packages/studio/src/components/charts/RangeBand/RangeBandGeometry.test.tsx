// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* eslint-disable testing-library/no-container, testing-library/no-node-access --
   Recharts draws the band and the center line as SVG <path> elements that carry no accessible
   role or text, so verifying their geometry means reading the rendered nodes directly. */

import { RangeBand } from '@studio/components/charts/RangeBand';
import { render, screen } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';

/** `ResponsiveContainer` measures the DOM, which jsdom reports as 0×0 — pin a size instead. */
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) =>
      cloneElement(children, { width: 800, height: 400 } as Record<string, unknown>),
  };
});

/** Pulls the y coordinate out of every `M`/`L` command in an SVG path. */
const pathYs = (d: string | null | undefined): number[] =>
  [...(d ?? '').matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map((match) => Number(match[2]));

const renderChart = (series: Parameters<typeof RangeBand>[0]['series'], xAxis: number[]) =>
  render(
    <RangeBand series={series} xAxis={xAxis} yAxisMin={0} yAxisMax={1} curve="linear" showMarks />
  );

describe('RangeBand geometry', () => {
  it('draws the center line inside the band rather than along its upper bound', () => {
    const { container } = renderChart(
      [{ id: 'a', label: 'A', data: [0.5, 0.5, 0.5], lower: [0, 0, 0], upper: [1, 1, 1] }],
      [0, 1, 2]
    );

    const bandYs = pathYs(container.querySelector('.recharts-area-area')?.getAttribute('d'));
    const lineYs = pathYs(container.querySelector('.recharts-line-curve')?.getAttribute('d'));
    expect(bandYs.length).toBeGreaterThan(0);
    expect(lineYs.length).toBe(3);

    // SVG y grows downward, so the band's upper bound is its smallest y.
    const top = Math.min(...bandYs);
    const bottom = Math.max(...bandYs);
    expect(lineYs.every((y) => y > top && y < bottom)).toBe(true);
    // A flat center line halfway between flat bounds lands on the midpoint.
    expect(new Set(lineYs).size).toBe(1);
    expect(lineYs[0]).toBeCloseTo((top + bottom) / 2, 0);
  });

  it('lets the line sit off-center and drift within a skewed band', () => {
    // A long upper tail early, collapsing later: the line rides the floor, then the ceiling.
    const { container } = renderChart(
      [{ id: 'a', label: 'A', data: [0.5, 0.5], lower: [0.4, 0.05], upper: [1, 0.55] }],
      [0, 1]
    );

    const band = pathYs(container.querySelector('.recharts-area-area')?.getAttribute('d'));
    const line = pathYs(container.querySelector('.recharts-line-curve')?.getAttribute('d'));
    // The band path runs along the upper bound and back along the lower, so the first and last
    // entries are the upper/lower bound at x=0.
    const [upperAtStart, upperAtEnd] = band;
    const [lowerAtEnd, lowerAtStart] = band.slice(2);

    // Fraction of the way down from the upper bound to the lower one.
    const depth = (y: number, upper: number, lower: number) => (y - upper) / (lower - upper);
    expect(depth(line[0], upperAtStart, lowerAtStart)).toBeGreaterThan(0.7);
    expect(depth(line[1], upperAtEnd, lowerAtEnd)).toBeLessThan(0.3);
  });

  it('keeps each series line on its own data when several bands overlap', () => {
    const { container } = renderChart(
      [
        { id: 'a', label: 'A', data: [0.5, 0.5], lower: [0.4, 0.4], upper: [0.6, 0.6] },
        { id: 'b', label: 'B', data: [0.2, 0.2], lower: [0.1, 0.1], upper: [0.3, 0.3] },
      ],
      [0, 1]
    );

    const lines = [...container.querySelectorAll('.recharts-line-curve')].map((node) =>
      pathYs(node.getAttribute('d'))
    );
    expect(lines).toHaveLength(2);
    // 0.5 and 0.2 are distinct, and neither sits on its band's 0.6 / 0.3 upper bound.
    const [first, second] = lines.map((ys) => ys[0]);
    expect(first).not.toBe(second);
    expect(second).toBeGreaterThan(first);
  });

  it('breaks the band at a gap instead of bridging it', () => {
    const { container } = renderChart(
      [
        {
          id: 'a',
          label: 'A',
          data: [0.5, 0.5, null, 0.5, 0.5],
          lower: [0.1, 0.1, null, 0.1, 0.1],
          upper: [0.9, 0.9, null, 0.9, 0.9],
        },
      ],
      [0, 1, 2, 3, 4]
    );

    // Two subpaths (each starting with `M`) on both the band and the line: the gap splits them
    // in the same place, rather than the band spanning a step the line skips.
    const bandD = container.querySelector('.recharts-area-area')?.getAttribute('d') ?? '';
    const lineD = container.querySelector('.recharts-line-curve')?.getAttribute('d') ?? '';
    expect(bandD.match(/M/g)).toHaveLength(2);
    expect(lineD.match(/M/g)).toHaveLength(2);
  });

  it('bridges a gap for a series that opted into connectNulls, marking only the real points', () => {
    // The gaps belong to the axis, not the curve, so the line spans them while the markers stay
    // on the steps a validation pass actually ran.
    const { container } = renderChart(
      [
        {
          id: 'validation',
          label: 'Validation',
          data: [0.2, null, null, 0.5, null],
          lower: [],
          upper: [],
          connectNulls: true,
        },
      ],
      [0, 1, 2, 3, 4]
    );

    const lineD = container.querySelector('.recharts-line-curve')?.getAttribute('d') ?? '';
    expect(lineD.match(/M/g)).toHaveLength(1);
    expect(container.querySelectorAll('.recharts-line-dot')).toHaveLength(2);
  });

  it('lets a sparse series turn its own markers on, whatever the chart-level default', () => {
    // The chart-level default measures the padded array, so a bridged series loses its markers
    // exactly when they are the only thing showing how rarely it was sampled.
    const { container } = render(
      <RangeBand
        series={[
          {
            id: 'validation',
            label: 'Validation',
            data: [0.2, null, null, 0.5, null],
            lower: [],
            upper: [],
            connectNulls: true,
            showMarks: true,
          },
        ]}
        xAxis={[0, 1, 2, 3, 4]}
        curve="linear"
      />
    );

    expect(container.querySelectorAll('.recharts-line-dot')).toHaveLength(2);
  });

  it('renders shared reference lines into the plot', () => {
    // Guards the cross-package render helper: recharts dispatches chart children by element
    // type, so if `renderReferenceLines` ever became a component the line would silently vanish.
    const { container } = render(
      <RangeBand
        series={[{ id: 'a', label: 'A', data: [0.5, 0.5], lower: [0.4, 0.4], upper: [0.6, 0.6] }]}
        xAxis={[0, 1]}
        yAxisMin={0}
        yAxisMax={1}
        referenceLines={[{ y: 0.8, label: 'Target' }]}
      />
    );

    expect(container.querySelector('.recharts-reference-line')).toBeInTheDocument();
  });

  it('drops a reference line the axis does not reach, and draws it once the caller makes room', () => {
    // Recharts discards a line outside the data-fitted domain, so a threshold needs the caller to
    // widen the axis; `extendDomain` cannot, as the explicit `domain` wins and the line escapes.
    const series = [{ id: 'a', label: 'A', data: [0.0001, 0.0005], lower: [], upper: [] }];
    const threshold = [{ y: 0.001, label: 'threshold 1e-3' }];

    const { container, rerender } = render(
      <RangeBand series={series} xAxis={[0, 1]} referenceLines={threshold} />
    );
    expect(container.querySelector('.recharts-reference-line')).toBeNull();

    rerender(
      <RangeBand series={series} xAxis={[0, 1]} referenceLines={threshold} yAxisMax={0.0011} />
    );
    expect(container.querySelector('.recharts-reference-line')).toBeInTheDocument();
    expect(screen.getByText('threshold 1e-3')).toBeInTheDocument();
  });

  it('draws no center line for a band-only series', () => {
    const { container } = renderChart(
      [{ id: 'a', label: 'A', lower: [0, 0], upper: [1, 1] }],
      [0, 1]
    );

    expect(container.querySelector('.recharts-area-area')).toBeInTheDocument();
    // `renderSeriesLines` skips band-only series rather than emitting an empty path element.
    expect(container.querySelector('.recharts-line-curve')).toBeNull();
  });
});
