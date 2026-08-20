// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { BaseChartProps, ChartXValue } from '@nemo/common/src/components/charts/types';

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

/**
 * A callout arrow drawn at one x position, typically spanning the gap between two series to call
 * out how far apart they are ("50X Higher Perf / Watt").
 */
export interface ComparisonAnnotation {
  /** Where on the x axis the callout sits. Must be one of the `xAxis` values. */
  x: ChartXValue;
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

export interface ComparisonLineChartProps extends BaseChartProps {
  series: ComparisonSeries[];
  /** Callout arrows spanning the gap between two series. */
  annotations?: ComparisonAnnotation[];
}
