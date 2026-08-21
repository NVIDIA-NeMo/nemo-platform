// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';

export type ChartXValue = string | number | Date;

/** Maps to recharts' `<Line type>`/`<Area type>`; `monotone` stays smooth without overshooting. */
export type ChartCurve = 'linear' | 'monotone' | 'step' | 'natural';

/** `time` is a numeric axis with time-spaced ticks — pick it when `xAxis` holds `Date`s. */
export type ChartXAxisType = 'category' | 'number' | 'time';

export interface ChartReferenceLine {
  /** Horizontal line at this y value. */
  y: number;
  label?: string;
  color?: string;
}

export interface ChartLegendItem {
  id: string;
  label: string;
  color: string;
  dashed?: boolean;
  hidden?: boolean;
}

/**
 * The frame every series chart shares — axes, legend, title, and the loading/empty states.
 * A chart extends this and adds its own `series` shape plus whatever marks it draws.
 */
export interface BaseChartProps {
  /** Shared x values. Length should match each series' data arrays. */
  xAxis: ChartXValue[];
  xAxisLabel?: string;
  yAxisLabel?: string;
  /** Overrides the axis type inferred from the first `xAxis` entry. */
  xAxisType?: ChartXAxisType;
  yAxisMin?: number;
  yAxisMax?: number;
  height?: number;
  curve?: ChartCurve;
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
  referenceLines?: ChartReferenceLine[];
  formatXValue?: (value: ChartXValue) => string;
  formatYValue?: (value: number) => string;
  loading?: boolean;
  emptyMessage?: string;
  /** Series hidden on first render; the user can re-enable them from the legend. */
  initialHiddenSeriesIds?: string[];
  onVisibleSeriesChange?: (visibleIds: string[]) => void;
  className?: string;
}
