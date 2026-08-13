// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BandRenderer, bandLegendArea } from '@studio/components/charts/ConfidenceBand';
import { render } from '@testing-library/react';
import { Area } from 'recharts';

const mockXScale = Object.assign((v: number) => v * 2, { range: () => [0, 1000] as number[] });
const mockYScale = Object.assign((v: number) => 300 - v * 300, {
  range: () => [300, 0] as number[],
});

const xAxisMap = { 0: { scale: mockXScale } };
const yAxisMap = { 0: { scale: mockYScale } };

const makeData = (steps: number[]) =>
  steps.map((step) => ({ step, lower: step * 0.001, upper: step * 0.002 }));

describe('bandLegendArea', () => {
  it('returns a recharts Area element', () => {
    const el = bandLegendArea({ upperKey: 'p75', name: 'Spread', fill: '#3d8a1e' });
    expect(el.type).toBe(Area);
  });

  it('forwards upperKey as dataKey, name, and fill onto the element props', () => {
    const el = bandLegendArea({ upperKey: 'upper', name: 'My band', fill: '#ff0000' });
    expect(el.props.dataKey).toBe('upper');
    expect(el.props.name).toBe('My band');
    expect(el.props.fill).toBe('#ff0000');
  });

  it('is invisible — fillOpacity and strokeOpacity are 0', () => {
    const el = bandLegendArea({ upperKey: 'p75', name: 'Spread', fill: '#3d8a1e' });
    expect(el.props.fillOpacity).toBe(0);
    expect(el.props.strokeOpacity).toBe(0);
  });

  it('uses legendType="square" so recharts adds it to the legend', () => {
    const el = bandLegendArea({ upperKey: 'p75', name: 'Spread', fill: '#3d8a1e' });
    expect(el.props.legendType).toBe('square');
  });
});

describe('BandRenderer', () => {
  it('returns null when xAxisMap is missing', () => {
    const { container } = render(
      <svg>
        <BandRenderer yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(container.querySelector('path')).toBeNull();
  });

  it('returns null when yAxisMap is missing', () => {
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(container.querySelector('path')).toBeNull();
  });

  it('returns null when fewer than 2 data points have both bounds', () => {
    const { container } = render(
      <svg>
        <BandRenderer
          xAxisMap={xAxisMap}
          yAxisMap={yAxisMap}
          data={[{ step: 0, lower: 0.1, upper: 0.5 }]}
        />
      </svg>
    );
    expect(container.querySelector('path')).toBeNull();
  });

  it('returns null when data has no points with the configured keys', () => {
    const { container } = render(
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
    expect(container.querySelector('path')).toBeNull();
  });

  it('renders a <path> when axes and data are valid', () => {
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(container.querySelector('path')).not.toBeNull();
  });

  it('applies fill and fillOpacity from props', () => {
    const { container } = render(
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
    const path = container.querySelector('path');
    expect(path?.getAttribute('fill')).toBe('#ff0000');
    expect(path?.getAttribute('fill-opacity')).toBe('0.3');
  });

  it('uses default fill and fillOpacity when omitted', () => {
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    const path = container.querySelector('path');
    expect(path?.getAttribute('fill')).toBe('#3d8a1e');
    expect(path?.getAttribute('fill-opacity')).toBe('0.5');
  });

  it('uses lowerKey and upperKey to read the correct fields', () => {
    const { container } = render(
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
    expect(container.querySelector('path')).not.toBeNull();
  });

  it('uses xKey to read the x-axis field', () => {
    const data = [
      { epoch: 1, lower: 0.1, upper: 0.5 },
      { epoch: 2, lower: 0.2, upper: 0.6 },
    ];
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={data} xKey="epoch" />
      </svg>
    );
    expect(container.querySelector('path')).not.toBeNull();
  });

  it('produces a closed SVG path (ends with Z)', () => {
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    const d = container.querySelector('path')?.getAttribute('d') ?? '';
    expect(d.trim().endsWith('Z')).toBe(true);
  });

  it('path encodes all upper-edge points and all lower-edge points', () => {
    const steps = [0, 100, 200, 300];
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData(steps)} />
      </svg>
    );
    const d = container.querySelector('path')?.getAttribute('d') ?? '';
    const coords = d.match(/\d+\.\d+,\d+\.\d+/g) ?? [];
    expect(coords).toHaveLength(steps.length * 2);
  });

  it('emits a clipPath rect when the scale exposes .range()', () => {
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={xAxisMap} yAxisMap={yAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(container.querySelector('clipPath rect')).not.toBeNull();
  });

  it('renders without a clipPath when the scale has no .range()', () => {
    const bareScale = (v: number) => v * 2;
    const bareAxisMap = { 0: { scale: bareScale } };
    const { container } = render(
      <svg>
        <BandRenderer xAxisMap={bareAxisMap} yAxisMap={bareAxisMap} data={makeData([0, 100, 200])} />
      </svg>
    );
    expect(container.querySelector('clipPath')).toBeNull();
    expect(container.querySelector('path')).not.toBeNull();
  });
});
