// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useRangeBand } from '@studio/components/charts/RangeBand';
import { BandRenderer } from '@studio/components/charts/RangeBand/BandRenderer';
import { render, renderHook, screen } from '@testing-library/react';
import { isValidElement, type ReactElement } from 'react';
import { Area, Customized } from 'recharts';

type El = ReactElement<Record<string, unknown>>;

const mockXScale = Object.assign((v: number) => v * 2, { range: () => [0, 1000] as number[] });
const mockYScale = Object.assign((v: number) => 300 - v * 300, {
  range: () => [300, 0] as number[],
});

const xAxisMap = { 0: { scale: mockXScale } };
const yAxisMap = { 0: { scale: mockYScale } };

const makeData = (steps: number[]) =>
  steps.map((step) => ({ step, lower: step * 0.001, upper: step * 0.002 }));

describe('useRangeBand', () => {
  it('returns null when enabled is false', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band', enabled: false }));
    expect(result.current).toBeNull();
  });

  it('returns an array of two React elements when enabled', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const nodes = result.current as El[];
    expect(Array.isArray(nodes)).toBe(true);
    expect(nodes).toHaveLength(2);
    expect(nodes.every((n) => isValidElement(n))).toBe(true);
  });

  it('first element is an Area for legend registration', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const [legend] = result.current as El[];
    expect(legend.type).toBe(Area);
  });

  it('Area uses upperKey as dataKey and is invisible', () => {
    const { result } = renderHook(() =>
      useRangeBand({ name: 'Band', upperKey: 'p75', fill: '#ff0000' })
    );
    const [legend] = result.current as El[];
    expect(legend.props.dataKey).toBe('p75');
    expect(legend.props.name).toBe('Band');
    expect(legend.props.fill).toBe('#ff0000');
    expect(legend.props.fillOpacity).toBe(0);
    expect(legend.props.strokeOpacity).toBe(0);
    expect(legend.props.legendType).toBe('square');
  });

  it('second element is a Customized renderer', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const [, renderer] = result.current as El[];
    expect(renderer.type).toBe(Customized);
  });

  it('Customized forwards lowerKey, upperKey, xKey, fill, fillOpacity', () => {
    const { result } = renderHook(() =>
      useRangeBand({
        name: 'Band',
        lowerKey: 'p25',
        upperKey: 'p75',
        xKey: 'epoch',
        fill: '#123456',
        fillOpacity: 0.3,
      })
    );
    const [, renderer] = result.current as El[];
    expect(renderer.props.lowerKey).toBe('p25');
    expect(renderer.props.upperKey).toBe('p75');
    expect(renderer.props.xKey).toBe('epoch');
    expect(renderer.props.fill).toBe('#123456');
    expect(renderer.props.fillOpacity).toBe(0.3);
  });

  it('applies default keys and fill when options are omitted', () => {
    const { result } = renderHook(() => useRangeBand({ name: 'Band' }));
    const [legend, renderer] = result.current as El[];
    expect(legend.props.dataKey).toBe('upper');
    expect(renderer.props.lowerKey).toBe('lower');
    expect(renderer.props.upperKey).toBe('upper');
    expect(renderer.props.xKey).toBe('step');
    expect(renderer.props.fill).toBe('#3d8a1e');
    expect(renderer.props.fillOpacity).toBe(0.5);
  });
});

describe('BandRenderer', () => {
  it('returns null when xAxisMap is missing', () => {
    render(
      <svg>
        <BandRenderer yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(screen.queryByTestId('range-band-path')).toBeNull();
  });

  it('returns null when yAxisMap is missing', () => {
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(screen.queryByTestId('range-band-path')).toBeNull();
  });

  it('returns null when fewer than 2 data points have both bounds', () => {
    render(
      <svg>
        <BandRenderer
          xAxisMap={xAxisMap}
          yAxisMap={yAxisMap}
          data={[{ step: 0, lower: 0.1, upper: 0.5 }]}
        />
      </svg>
    );
    expect(screen.queryByTestId('range-band-path')).toBeNull();
  });

  it('returns null when data has no points with the configured keys', () => {
    render(
      <svg>
        <BandRenderer
          xAxisMap={xAxisMap}
          yAxisMap={yAxisMap}
          data={[
            { step: 0, p25: 0.1, p75: 0.5 },
            { step: 100, p25: 0.2, p75: 0.6 },
          ]}
          lowerKey="lower"
          upperKey="upper"
        />
      </svg>
    );
    expect(screen.queryByTestId('range-band-path')).toBeNull();
  });

  it('renders a path when axes and data are valid', () => {
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(screen.getByTestId('range-band-path')).toBeInTheDocument();
  });

  it('applies fill and fillOpacity from props', () => {
    render(
      <svg>
        <BandRenderer
          xAxisMap={xAxisMap}
          yAxisMap={yAxisMap}
          data={makeData([0, 100, 200])}
          fill="#ff0000"
          fillOpacity={0.3}
        />
      </svg>
    );
    const path = screen.getByTestId('range-band-path');
    expect(path.getAttribute('fill')).toBe('#ff0000');
    expect(path.getAttribute('fill-opacity')).toBe('0.3');
  });

  it('uses default fill and fillOpacity when omitted', () => {
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    const path = screen.getByTestId('range-band-path');
    expect(path.getAttribute('fill')).toBe('#3d8a1e');
    expect(path.getAttribute('fill-opacity')).toBe('0.5');
  });

  it('uses lowerKey and upperKey to read the correct fields', () => {
    render(
      <svg>
        <BandRenderer
          xAxisMap={xAxisMap}
          yAxisMap={yAxisMap}
          data={[
            { step: 0, a: 0.1, b: 0.5 },
            { step: 100, a: 0.2, b: 0.6 },
          ]}
          lowerKey="a"
          upperKey="b"
        />
      </svg>
    );
    expect(screen.getByTestId('range-band-path')).toBeInTheDocument();
  });

  it('uses xKey to read the x-axis field', () => {
    const data = [
      { epoch: 1, lower: 0.1, upper: 0.5 },
      { epoch: 2, lower: 0.2, upper: 0.6 },
    ];
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={data} xKey="epoch" />
      </svg>
    );
    expect(screen.getByTestId('range-band-path')).toBeInTheDocument();
  });

  it('produces a closed SVG path (ends with Z)', () => {
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    const d = screen.getByTestId('range-band-path').getAttribute('d') ?? '';
    expect(d.trim().endsWith('Z')).toBe(true);
  });

  it('path encodes all upper-edge and lower-edge points', () => {
    const steps = [0, 100, 200, 300];
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData(steps)} />
      </svg>
    );
    const d = screen.getByTestId('range-band-path').getAttribute('d') ?? '';
    const coords = d.match(/\d+\.\d+,\d+\.\d+/g) ?? [];
    expect(coords).toHaveLength(steps.length * 2);
  });

  it('emits a clipPath when the scale exposes .range()', () => {
    render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(screen.getByTestId('range-band-clip')).toBeInTheDocument();
  });

  it('renders without a clipPath when the scale has no .range()', () => {
    const bareScale = (v: number) => v * 2;
    const bareAxisMap = { 0: { scale: bareScale } };
    render(
      <svg>
        <BandRenderer
          xAxisMap={bareAxisMap}
          yAxisMap={bareAxisMap}
          data={makeData([0, 100, 200])}
        />
      </svg>
    );
    expect(screen.queryByTestId('range-band-clip')).toBeNull();
    expect(screen.getByTestId('range-band-path')).toBeInTheDocument();
  });
});
