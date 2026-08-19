// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FADED_SERIES_OPACITY } from '@nemo/common/src/components/charts/tokens';
import type { ChartCurve } from '@nemo/common/src/components/charts/types';
import type { ColoredBandSeries } from '@studio/components/charts/RangeBand/types';
import { hasCenterLine, lowerKeyFor, upperKeyFor } from '@studio/components/charts/RangeBand/utils';
import type { ReactElement } from 'react';
import { Area, Line } from 'recharts';

/**
 * Plain functions, not components: recharts inspects each chart child's element type, so a wrapper
 * would hide the `<Area>`/`<Line>`. Keys are namespaced per layer, or recharts mismatches points.
 */

export interface BandAreaOptions {
  name: string;
  lowerKey: string;
  upperKey: string;
  fill: string;
  fillOpacity: number;
  type: ChartCurve;
  key?: string;
}

/**
 * Recharts fills an `<Area>` as a band when its value is a `[min, max]` tuple. No `connectNulls`:
 * a missing bound breaks the band rather than bridging a step that was never measured.
 * @see https://recharts.github.io/en-US/examples/BandedChart
 */
export const bandArea = ({
  key,
  name,
  lowerKey,
  upperKey,
  fill,
  fillOpacity,
  type,
}: BandAreaOptions): ReactElement => (
  <Area
    key={key}
    dataKey={(row: Record<string, unknown>) => {
      const lower = row[lowerKey];
      const upper = row[upperKey];
      return typeof lower === 'number' &&
        Number.isFinite(lower) &&
        typeof upper === 'number' &&
        Number.isFinite(upper)
        ? [lower, upper]
        : undefined;
    }}
    type={type}
    stroke="none"
    fill={fill}
    fillOpacity={fillOpacity}
    legendType="square"
    name={name}
    isAnimationActive={false}
    activeDot={false}
    dot={false}
  />
);

interface RenderBandsOptions {
  type: ChartCurve;
  /** Fades every other band so a single series can be read out of a crowded chart. */
  hoveredId: string | null;
  bandOpacity: number;
}

export const renderBands = (
  series: ColoredBandSeries[],
  { type, hoveredId, bandOpacity }: RenderBandsOptions
): ReactElement[] =>
  series.map((entry) => {
    const opacity = entry.bandOpacity ?? bandOpacity;
    return bandArea({
      key: `band-${entry.id}`,
      name: entry.label,
      lowerKey: lowerKeyFor(entry.id),
      upperKey: upperKeyFor(entry.id),
      fill: entry.resolvedColor,
      // Never brighten a band that is already fainter than the faded level.
      fillOpacity:
        hoveredId && hoveredId !== entry.id ? Math.min(opacity, FADED_SERIES_OPACITY) : opacity,
      type,
    });
  });

interface SeriesLineOptions {
  curve: ChartCurve;
  hoveredId: string | null;
  showMarks?: boolean;
}

/**
 * Local rather than shared with the comparison line chart: this copy skips band-only series and
 * namespaces its key, neither of which that chart may do.
 */
export const renderSeriesLines = (
  series: ColoredBandSeries[],
  { curve, hoveredId, showMarks }: SeriesLineOptions
): ReactElement[] =>
  series
    .filter(hasCenterLine)
    .map((entry) => (
      <Line
        key={`line-${entry.id}`}
        type={curve}
        dataKey={entry.id}
        name={entry.label}
        stroke={entry.resolvedColor}
        strokeWidth={2}
        strokeDasharray={entry.dashed ? '6 4' : undefined}
        strokeOpacity={hoveredId && hoveredId !== entry.id ? FADED_SERIES_OPACITY : 1}
        dot={showMarks ?? (entry.data?.length ?? 0) <= 3}
        activeDot={{ r: 4 }}
        connectNulls={false}
        isAnimationActive={false}
      />
    ));
