// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { BaseChartProps } from '@nemo/common/src/components/charts/types';

/**
 * A shaded band between two bounds, optionally with a center line through it. The line comes from
 * `data` alone, so it is free to sit anywhere inside the band.
 */
export interface RangeBandSeries {
  /** Stable identifier; also the row key in the chart data and the legend toggle key. */
  id: string;
  label: string;
  /** Center line values, one per x value. Omit for a band with no line through it. */
  data?: (number | null)[];
  /** Lower bound of the band, one per x value. `null` drops that point from the band. */
  lower: (number | null)[];
  /** Upper bound of the band, one per x value. `null` drops that point from the band. */
  upper: (number | null)[];
  /** CSS color. Defaults to the shared palette, assigned by index. */
  color?: string;
  /** Renders the center line dashed — use for baselines and targets. */
  dashed?: boolean;
  /** Overrides the chart-level `bandOpacity` for this series. */
  bandOpacity?: number;
  /** Formats this series' values in the tooltip. Falls back to the chart-level formatter. */
  valueFormatter?: (value: number | null) => string;
}

export interface ColoredBandSeries extends RangeBandSeries {
  resolvedColor: string;
}

export interface RangeBandProps extends BaseChartProps {
  series: RangeBandSeries[];
  /** Fill opacity applied to every band; a series can override it with its own `bandOpacity`. */
  bandOpacity?: number;
}
