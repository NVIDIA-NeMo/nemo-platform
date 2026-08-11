// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ComparisonLineChart } from '@nemo/common/src/components/ComparisonLineChart';
import type { ComparisonSeries } from '@nemo/common/src/components/ComparisonLineChart/types';
import {
  buildChartRows,
  formatNumericValue,
  hasPlottableData,
  inferXAxisType,
  resolveAnnotation,
  seriesColor,
} from '@nemo/common/src/components/ComparisonLineChart/utils';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';

const series: ComparisonSeries[] = [
  { id: 'baseline', label: 'Baseline', data: [0.4, 0.5, 0.55], dashed: true },
  { id: 'candidate', label: 'Candidate', data: [0.45, 0.6, 0.72] },
];

const xAxis = ['Step 1', 'Step 2', 'Step 3'];

describe('ComparisonLineChart', () => {
  it('renders a legend entry per series', () => {
    render(<ComparisonLineChart series={series} xAxis={xAxis} />);

    expect(screen.getByRole('button', { name: 'Baseline' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Candidate' })).toBeInTheDocument();
  });

  it('toggles a series off and reports the remaining visible ids', async () => {
    const user = userEvent.setup();
    const onVisibleSeriesChange = vi.fn();
    render(
      <ComparisonLineChart
        series={series}
        xAxis={xAxis}
        onVisibleSeriesChange={onVisibleSeriesChange}
      />
    );

    const baseline = screen.getByRole('button', { name: 'Baseline' });
    expect(baseline).toHaveAttribute('aria-pressed', 'true');

    await user.click(baseline);

    expect(baseline).toHaveAttribute('aria-pressed', 'false');
    expect(onVisibleSeriesChange).toHaveBeenCalledWith(['candidate']);
  });

  it('notifies once for a toggle in Strict Mode', async () => {
    const user = userEvent.setup();
    const onVisibleSeriesChange = vi.fn();
    render(
      <StrictMode>
        <ComparisonLineChart
          series={series}
          xAxis={xAxis}
          onVisibleSeriesChange={onVisibleSeriesChange}
        />
      </StrictMode>
    );

    await user.click(screen.getByRole('button', { name: 'Baseline' }));

    expect(onVisibleSeriesChange).toHaveBeenCalledTimes(1);
    expect(onVisibleSeriesChange).toHaveBeenCalledWith(['candidate']);
  });

  it('keeps hidden series in the legend so they can be restored', async () => {
    const user = userEvent.setup();
    render(
      <ComparisonLineChart series={series} xAxis={xAxis} initialHiddenSeriesIds={['candidate']} />
    );

    const candidate = screen.getByRole('button', { name: 'Candidate' });
    expect(candidate).toHaveAttribute('aria-pressed', 'false');

    await user.click(candidate);

    expect(candidate).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders the title alongside the legend', () => {
    render(<ComparisonLineChart series={series} xAxis={xAxis} title="Daily averages" />);

    expect(screen.getByText('Daily averages')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Baseline' })).toBeInTheDocument();
  });

  it('still renders the legend when positioned below the plot', async () => {
    const user = userEvent.setup();
    render(<ComparisonLineChart series={series} xAxis={xAxis} legendPosition="bottom" />);

    const baseline = screen.getByRole('button', { name: 'Baseline' });
    await user.click(baseline);

    expect(baseline).toHaveAttribute('aria-pressed', 'false');
  });

  it('hides the legend when disabled', () => {
    render(<ComparisonLineChart series={series} xAxis={xAxis} showLegend={false} />);

    expect(screen.queryByRole('button', { name: 'Baseline' })).not.toBeInTheDocument();
  });

  it('renders the empty message when every value is null', () => {
    render(
      <ComparisonLineChart
        series={[{ id: 'a', label: 'A', data: [null, null] }]}
        xAxis={['x', 'y']}
        emptyMessage="Nothing to compare yet"
      />
    );

    expect(screen.getByText('Nothing to compare yet')).toBeInTheDocument();
  });

  it('keeps the axis labels and a static legend in the empty state', () => {
    render(
      <ComparisonLineChart
        series={series}
        xAxis={[]}
        xAxisLabel="Step"
        yAxisLabel="Accuracy"
        emptyMessage="No runs yet"
      />
    );

    expect(screen.getByText('No runs yet')).toBeInTheDocument();
    const baseline = screen.getByRole('button', { name: 'Baseline' });
    expect(baseline).toBeDisabled();
  });

  it('renders a skeleton while loading', () => {
    render(<ComparisonLineChart series={series} xAxis={xAxis} loading />);

    expect(screen.getByTestId('comparison-line-chart-skeleton')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Baseline' })).not.toBeInTheDocument();
  });
});

describe('ComparisonLineChart utils', () => {
  it('infers the axis type from the first x value', () => {
    expect(inferXAxisType(['a', 'b'])).toBe('category');
    expect(inferXAxisType([1, 2])).toBe('number');
    expect(inferXAxisType([new Date(0)])).toBe('time');
  });

  it('pivots parallel series data into recharts rows', () => {
    expect(buildChartRows(series, xAxis)).toEqual([
      { x: 'Step 1', baseline: 0.4, candidate: 0.45 },
      { x: 'Step 2', baseline: 0.5, candidate: 0.6 },
      { x: 'Step 3', baseline: 0.55, candidate: 0.72 },
    ]);
  });

  it('nulls out gaps, non-finite values, and short series in rows', () => {
    expect(
      buildChartRows([{ id: 'a', label: 'A', data: [1, Number.NaN] }], [new Date(0), 'x', 'y'])
    ).toEqual([
      { x: 0, a: 1 },
      { x: 'x', a: null },
      { x: 'y', a: null },
    ]);
  });

  it('rejects reserved and duplicate series ids before constructing rows', () => {
    expect(() => buildChartRows([{ id: 'x', label: 'X', data: [1] }], ['a'])).toThrow(
      'Series id "x" is reserved for the x axis.'
    );
    expect(() =>
      buildChartRows(
        [
          { id: 'a', label: 'First', data: [1] },
          { id: 'a', label: 'Second', data: [2] },
        ],
        ['a']
      )
    ).toThrow('Duplicate series id: a');
  });

  it('treats null-only and empty input as unplottable', () => {
    expect(hasPlottableData(series, xAxis)).toBe(true);
    expect(hasPlottableData([{ id: 'a', label: 'A', data: [null] }], ['x'])).toBe(false);
    expect(hasPlottableData([{ id: 'a', label: 'A', data: [null, 1] }], ['x'])).toBe(false);
    expect(hasPlottableData(series, [])).toBe(false);
  });

  it('prefers an explicit series color over the palette', () => {
    expect(seriesColor({ id: 'a', label: 'A', data: [], color: '#fff' }, 0)).toBe('#fff');
    expect(seriesColor({ id: 'a', label: 'A', data: [] }, 0)).toBe('var(--text-color-accent-blue)');
  });

  it('resolves an annotation between two series and derives the multiplier', () => {
    expect(
      resolveAnnotation({ x: 'Step 3', betweenSeriesIds: ['baseline', 'candidate'] }, series, xAxis)
    ).toEqual({
      x: 'Step 3',
      fromY: 0.55,
      toY: 0.72,
      label: '1.3X',
      description: undefined,
      color: undefined,
      pointsUp: true,
      labelSide: 'left',
    });
  });

  it('flips the callout text inward for annotations near the right edge', () => {
    const between: [string, string] = ['baseline', 'candidate'];
    const sideAt = (x: string) =>
      resolveAnnotation({ x, betweenSeriesIds: between }, series, xAxis)?.labelSide;

    expect(sideAt('Step 1')).toBe('right');
    expect(sideAt('Step 3')).toBe('left');
    expect(
      resolveAnnotation(
        { x: 'Step 3', betweenSeriesIds: between, labelSide: 'right' },
        series,
        xAxis
      )?.labelSide
    ).toBe('right');
  });

  it('points the annotation down when the target series is lower', () => {
    expect(
      resolveAnnotation({ x: 'Step 1', betweenSeriesIds: ['candidate', 'baseline'] }, series, xAxis)
        ?.pointsUp
    ).toBe(false);
  });

  it('rounds large multipliers to whole numbers', () => {
    const wide = [
      { id: 'low', label: 'Low', data: [55_000] },
      { id: 'high', label: 'High', data: [2_550_000] },
    ];
    expect(resolveAnnotation({ x: 0, betweenSeriesIds: ['low', 'high'] }, wide, [0])?.label).toBe(
      '46X'
    );
  });

  it('drops annotations whose x value or endpoint is missing', () => {
    expect(
      resolveAnnotation({ x: 'Step 9', betweenSeriesIds: ['baseline', 'candidate'] }, series, xAxis)
    ).toBeNull();
    expect(
      resolveAnnotation({ x: 'Step 1', betweenSeriesIds: ['baseline', 'ghost'] }, series, xAxis)
    ).toBeNull();
  });

  it('compacts large values and keeps small ones precise', () => {
    expect(formatNumericValue(16000)).toBe('16K');
    expect(formatNumericValue(0.1234)).toBe('0.123');
  });
});
