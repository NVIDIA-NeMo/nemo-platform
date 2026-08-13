// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';

export type ComparisonXValue = string | number | Date;

/** Maps to recharts' `<Line type>`; `monotone` keeps comparison lines smooth without overshooting. */
export type ComparisonCurve = 'linear' | 'monotone' | 'step' | 'natural';

/** `time` is a numeric axis with time-spaced ticks — pick it when `xAxis` holds `Date`s. */
export type ComparisonXAxisType = 'category' | 'number' | 'time';

export interface ComparisonSeries {
  /** Stable identifier; also the row key in the chart data and the legend toggle key. */
  id: string;
  label: string;
  /** One entry per x value. `null` renders a gap. */
  data: (number | null)[];
  /** CSS color. Defaults to the shared palette, assigned by index. */
  color?: string;
  /** Renders the line dashed — use for baselines and targets. */
  dashed?: boolean;
  /** Formats this series' values in the tooltip. Falls back to the chart-level formatter. */
  valueFormatter?: (value: number | null) => string;
}

export interface ComparisonReferenceLine {
  /** Horizontal line at this y value. */
  y: number;
  label?: string;
  color?: string;
}

/**
 * A callout arrow drawn at one x position, typically spanning the gap between two series to call
 * out how far apart they are ("50X Higher Perf / Watt").
 */
export interface ComparisonAnnotation {
  /** Where on the x axis the callout sits. Must be one of the `xAxis` values. */
  x: ComparisonXValue;
  /** `[fromSeriesId, toSeriesId]` — the arrow runs from the first series' value to the second's. */
  betweenSeriesIds?: [string, string];
  /** Explicit endpoints, for callouts not tied to two series. Ignored when `betweenSeriesIds` is set. */
  fromY?: number;
  toY?: number;
  /** Headline text. Defaults to the ratio between the endpoints, e.g. `50X`. */
  label?: string;
  /** Smaller supporting text under the headline. */
  description?: string;
  color?: string;
  /**
   * Which side of the arrow the text sits on. Defaults to `right`, flipping to `left` for
   * annotations in the last third of the x axis so the text stays inside the chart.
   */
  labelSide?: 'left' | 'right';
}

export interface ComparisonLineChartProps {
  series: ComparisonSeries[];
  /** Shared x values. Length should match each series' `data`. */
  xAxis: ComparisonXValue[];
  xAxisLabel?: string;
  yAxisLabel?: string;
  /** Overrides the axis type inferred from the first `xAxis` entry. */
  xAxisType?: ComparisonXAxisType;
  yAxisMin?: number;
  yAxisMax?: number;
  height?: number;
  curve?: ComparisonCurve;
  showGrid?: boolean;
  showLegend?: boolean;
  /** `top` puts the legend right-aligned in a header row above the plot, opposite `title`. */
  legendPosition?: 'top' | 'bottom';
  /** Optional heading rendered at the left of the legend row. */
  title?: ReactNode;
  /** Legend entries stay clickable; toggling hides the series without unmounting the chart. */
  legendInteractive?: boolean;
  /** Forces point markers on or off. Defaults to on only for very short series. */
  showMarks?: boolean;
  referenceLines?: ComparisonReferenceLine[];
  annotations?: ComparisonAnnotation[];
  formatXValue?: (value: ComparisonXValue) => string;
  formatYValue?: (value: number) => string;
  loading?: boolean;
  emptyMessage?: string;
  /** Series hidden on first render; the user can re-enable them from the legend. */
  initialHiddenSeriesIds?: string[];
  onVisibleSeriesChange?: (visibleIds: string[]) => void;
  className?: string;
}
