// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { inferXAxisType, seriesColor } from '@nemo/common/src/components/charts/format';
import { RangeBand, useRangeBand } from '@studio/components/charts/RangeBand';
import { RangeBandTooltip } from '@studio/components/charts/RangeBand/RangeBandTooltip';
import type { ColoredBandSeries, RangeBandSeries } from '@studio/components/charts/RangeBand/types';
import {
  buildRangeBandRows,
  hasCenterLine,
  hasPlottableBands,
  lowerKeyFor,
  upperKeyFor,
} from '@studio/components/charts/RangeBand/utils';
import { render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { isValidElement, type ReactElement } from 'react';
import { Area } from 'recharts';

type El = ReactElement<Record<string, unknown>>;

const series: RangeBandSeries[] = [
  {
    id: 'baseline',
    label: 'Baseline',
    data: [0.4, 0.5, 0.55],
    lower: [0.3, 0.42, 0.5],
    upper: [0.5, 0.58, 0.6],
    dashed: true,
  },
  {
    id: 'candidate',
    label: 'Candidate',
    data: [0.45, 0.6, 0.72],
    lower: [0.35, 0.5, 0.65],
    upper: [0.55, 0.7, 0.79],
  },
];

const xAxis = ['Step 1', 'Step 2', 'Step 3'];

describe('RangeBand', () => {
  it('renders a legend entry per series', () => {
    render(<RangeBand series={series} xAxis={xAxis} />);

    expect(screen.getByRole('button', { name: 'Baseline' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Candidate' })).toBeInTheDocument();
  });

  it('toggles a series off and reports the remaining visible ids', async () => {
    const user = userEvent.setup();
    const onVisibleSeriesChange = vi.fn();
    render(
      <RangeBand series={series} xAxis={xAxis} onVisibleSeriesChange={onVisibleSeriesChange} />
    );

    const baseline = screen.getByRole('button', { name: 'Baseline' });
    expect(baseline).toHaveAttribute('aria-pressed', 'true');

    await user.click(baseline);

    expect(baseline).toHaveAttribute('aria-pressed', 'false');
    expect(onVisibleSeriesChange).toHaveBeenCalledWith(['candidate']);
  });

  it('renders the title alongside the legend', () => {
    render(<RangeBand series={series} xAxis={xAxis} title="Training accuracy" />);

    expect(screen.getByText('Training accuracy')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Baseline' })).toBeInTheDocument();
  });

  it('still renders the legend when positioned below the plot', async () => {
    const user = userEvent.setup();
    render(<RangeBand series={series} xAxis={xAxis} legendPosition="bottom" />);

    const baseline = screen.getByRole('button', { name: 'Baseline' });
    await user.click(baseline);

    expect(baseline).toHaveAttribute('aria-pressed', 'false');
  });

  it('hides the legend when disabled', () => {
    render(<RangeBand series={series} xAxis={xAxis} showLegend={false} />);

    expect(screen.queryByRole('button', { name: 'Baseline' })).not.toBeInTheDocument();
  });

  it('plots a band-only series that has no center line', () => {
    render(
      <RangeBand
        series={[{ id: 'spread', label: 'Spread', lower: [0.1, 0.2], upper: [0.4, 0.5] }]}
        xAxis={['a', 'b']}
      />
    );

    expect(screen.getByRole('button', { name: 'Spread' })).toBeInTheDocument();
  });

  it('renders the empty message when every value is null', () => {
    render(
      <RangeBand
        series={[
          { id: 'a', label: 'A', data: [null, null], lower: [null, null], upper: [null, null] },
        ]}
        xAxis={['x', 'y']}
        emptyMessage="Nothing to compare yet"
      />
    );

    expect(screen.getByText('Nothing to compare yet')).toBeInTheDocument();
  });

  it('keeps the title and a static legend in the empty state', () => {
    render(
      <RangeBand series={series} xAxis={[]} title="Training accuracy" emptyMessage="No runs yet" />
    );

    expect(screen.getByText('No runs yet')).toBeInTheDocument();
    expect(screen.getByText('Training accuracy')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Baseline' })).toBeDisabled();
  });

  it('renders a skeleton while loading', () => {
    render(<RangeBand series={series} xAxis={xAxis} loading />);

    expect(screen.getByTestId('range-band-skeleton')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Baseline' })).not.toBeInTheDocument();
  });
});

describe('RangeBandTooltip', () => {
  const tooltipSeries: ColoredBandSeries[] = [
    {
      id: 'a',
      label: 'Candidate',
      resolvedColor: '#00aaff',
      data: [0.5],
      lower: [0.4],
      upper: [0.62],
    },
    { id: 'b', label: 'Band only', resolvedColor: '#88cc00', lower: [0.1], upper: [0.3] },
  ];
  const row = {
    x: 3,
    a: 0.5,
    a__lower: 0.4,
    a__upper: 0.62,
    b: null,
    b__lower: 0.1,
    b__upper: 0.3,
  };

  const renderTooltip = (props: Partial<Parameters<typeof RangeBandTooltip>[0]> = {}) =>
    render(
      <RangeBandTooltip
        active
        label={3}
        payload={[{ payload: row }] as never}
        series={tooltipSeries}
        formatLabel={(value) => `Step ${value}`}
        formatValue={(_id, value) => (value === null ? '—' : value.toFixed(2))}
        {...props}
      />
    );

  it('shows the center value and the band range for each series', () => {
    renderTooltip();

    expect(screen.getByText('Step 3')).toBeInTheDocument();
    expect(screen.getByText('Candidate')).toBeInTheDocument();
    expect(screen.getByText('0.50')).toBeInTheDocument();
    expect(screen.getByText('0.40 – 0.62')).toBeInTheDocument();
  });

  it('omits the center value for a series that only has bounds', () => {
    renderTooltip();

    expect(screen.getByText('Band only')).toBeInTheDocument();
    expect(screen.getByText('0.10 – 0.30')).toBeInTheDocument();
    // 'b' has a null center, so no value sits next to its label.
    expect(screen.queryByText('—')).not.toBeInTheDocument();
  });

  it('renders nothing when inactive, empty, or with no values at the hovered row', () => {
    const { container: inactive } = renderTooltip({ active: false });
    expect(inactive).toBeEmptyDOMElement();

    const { container: empty } = renderTooltip({ payload: [] });
    expect(empty).toBeEmptyDOMElement();

    const { container: blank } = renderTooltip({
      payload: [{ payload: { x: 9 } }] as never,
    });
    expect(blank).toBeEmptyDOMElement();
  });
});

describe('RangeBand utils', () => {
  it('suffixes bound keys so they cannot collide with the series id', () => {
    expect(lowerKeyFor('candidate')).toBe('candidate__lower');
    expect(upperKeyFor('candidate')).toBe('candidate__upper');
  });

  it('pivots each series center and bounds into recharts rows', () => {
    expect(buildRangeBandRows([series[1]], ['Step 1', 'Step 2'])).toEqual([
      { x: 'Step 1', candidate: 0.45, candidate__lower: 0.35, candidate__upper: 0.55 },
      { x: 'Step 2', candidate: 0.6, candidate__lower: 0.5, candidate__upper: 0.7 },
    ]);
  });

  it('nulls out missing and non-finite values, and converts dates to timestamps', () => {
    const sparse: RangeBandSeries = {
      id: 'a',
      label: 'A',
      data: [1, Number.NaN],
      lower: [Number.NaN, 0.2],
      upper: [0.5, Number.POSITIVE_INFINITY],
    };

    expect(buildRangeBandRows([sparse], [new Date(0), 'x', 'y'])).toEqual([
      { x: 0, a: 1, a__lower: null, a__upper: 0.5 },
      { x: 'x', a: null, a__lower: 0.2, a__upper: null },
      { x: 'y', a: null, a__lower: null, a__upper: null },
    ]);
  });

  it('rejects reserved, suffixed, and duplicate series ids', () => {
    const bounds = { lower: [0.1], upper: [0.9] };
    expect(() => buildRangeBandRows([{ id: 'x', label: 'X', ...bounds }], ['a'])).toThrow(
      'Series id "x" is reserved for the x axis.'
    );
    expect(() =>
      buildRangeBandRows([{ id: 'foo__lower', label: 'Foo', ...bounds }], ['a'])
    ).toThrow('Series id "foo__lower" ends with a reserved band-bound suffix.');
    expect(() =>
      buildRangeBandRows([{ id: 'foo__upper', label: 'Foo', ...bounds }], ['a'])
    ).toThrow('reserved band-bound suffix');
    expect(() =>
      buildRangeBandRows(
        [
          { id: 'a', label: 'First', ...bounds },
          { id: 'a', label: 'Second', ...bounds },
        ],
        ['a']
      )
    ).toThrow('Duplicate series id: a');
  });

  it('resolves series colors from the palette unless one is given', () => {
    expect(seriesColor({ id: 'a', label: 'A', lower: [], upper: [] }, 0)).toBe(
      'var(--text-color-accent-blue)'
    );
    expect(seriesColor({ id: 'a', label: 'A', lower: [], upper: [], color: '#fff' }, 0)).toBe(
      '#fff'
    );
  });

  it('infers the axis type from the first x value', () => {
    expect(inferXAxisType(['a', 'b'])).toBe('category');
    expect(inferXAxisType([1, 2])).toBe('number');
    expect(inferXAxisType([new Date(0)])).toBe('time');
  });

  it('reports whether a series has a center line to draw', () => {
    expect(hasCenterLine({ id: 'a', label: 'A', lower: [0.1], upper: [0.9] })).toBe(false);
    expect(hasCenterLine({ id: 'a', label: 'A', data: [null], lower: [0.1], upper: [0.9] })).toBe(
      false
    );
    expect(hasCenterLine({ id: 'a', label: 'A', data: [0.5], lower: [0.1], upper: [0.9] })).toBe(
      true
    );
  });

  it('treats a series with only bounds as plottable', () => {
    expect(hasPlottableBands([{ id: 'a', label: 'A', lower: [0.1], upper: [0.4] }], ['x'])).toBe(
      true
    );
  });

  it('treats null-only and empty input as unplottable', () => {
    expect(hasPlottableBands(series, xAxis)).toBe(true);
    expect(
      hasPlottableBands(
        [{ id: 'a', label: 'A', data: [null], lower: [null], upper: [null] }],
        ['x']
      )
    ).toBe(false);
    expect(hasPlottableBands(series, [])).toBe(false);
  });

  it('ignores values past the end of the x axis', () => {
    expect(
      hasPlottableBands([{ id: 'a', label: 'A', lower: [null, 0.2], upper: [null, 0.4] }], ['x'])
    ).toBe(false);
  });
});

describe('useRangeBand', () => {
  it('returns null when enabled is false', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band', enabled: false }));
    expect(result.current).toBeNull();
  });

  it('returns a single Area element when enabled', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const band = result.current as El;
    expect(isValidElement(band)).toBe(true);
    expect(band.type).toBe(Area);
  });

  it('applies default keys, fill, fillOpacity, and type when options are omitted', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const band = result.current as El;
    expect(typeof band.props.dataKey).toBe('function');
    expect(band.props.name).toBe('Band');
    expect(band.props.fill).toBe('var(--text-color-accent-green)');
    expect(band.props.fillOpacity).toBe(0.5);
    expect(band.props.type).toBe('monotone');
    expect(band.props.stroke).toBe('none');
    expect(band.props.legendType).toBe('square');
    expect(band.props.activeDot).toBe(false);
    expect(band.props.dot).toBe(false);
  });

  it('forwards a custom fill, fillOpacity, and type', () => {
    const { result } = renderHook(() =>
      useRangeBand({ name: 'Band', fill: '#ff0000', fillOpacity: 0.3, type: 'linear' })
    );
    const band = result.current as El;
    expect(band.props.fill).toBe('#ff0000');
    expect(band.props.fillOpacity).toBe(0.3);
    expect(band.props.type).toBe('linear');
  });

  it('dataKey returns [lower, upper] for valid points, undefined otherwise', () => {
    const { result } = renderHook(() =>
      useRangeBand({ name: 'Band', lowerKey: 'lo', upperKey: 'hi' })
    );
    const band = result.current as El;
    const fn = band.props.dataKey as (d: Record<string, unknown>) => unknown;
    expect(fn({ lo: -0.5, hi: 0.8 })).toEqual([-0.5, 0.8]);
    expect(fn({ lo: NaN, hi: 0.8 })).toBeUndefined();
    expect(fn({ lo: -0.5, hi: Infinity })).toBeUndefined();
    expect(fn({ lo: null, hi: 0.8 })).toBeUndefined();
  });

  it('dataKey uses default lower/upper keys', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const band = result.current as El;
    const fn = band.props.dataKey as (d: Record<string, unknown>) => unknown;
    expect(fn({ step: 0, lower: -0.25, upper: 0.1 })).toEqual([-0.25, 0.1]);
  });
});
