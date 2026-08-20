// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SERIES_COLORS } from '@nemo/common/src/components/charts/tokens';
import type { ChartXAxisType, ChartXValue } from '@nemo/common/src/components/charts/types';

/**
 * `T &` rather than `T extends`: a constraint makes TypeScript resolve `T` to the constraint and
 * reject extra properties on the fresh object literals both chart suites pass in.
 */
export const seriesColor = <T>(series: T & { color?: string }, index: number): string =>
  series.color ?? SERIES_COLORS[index % SERIES_COLORS.length];

export const inferXAxisType = (xAxis: ChartXValue[]): ChartXAxisType => {
  const first = xAxis.find((value) => value !== undefined && value !== null);
  if (first instanceof Date) return 'time';
  if (typeof first === 'number') return 'number';
  return 'category';
};

/** Dates become timestamps so recharts can place them on a numeric axis. */
export const toPlotValue = (value: ChartXValue): string | number =>
  value instanceof Date ? value.getTime() : value;

/** Compacts large magnitudes (16000 -> "16K") while keeping small values precise. */
export const formatNumericValue = (value: number): string =>
  Math.abs(value) >= 1000
    ? value.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })
    : value.toLocaleString(undefined, { maximumFractionDigits: 3 });

export const formatXValueDefault = (value: ChartXValue): string => {
  if (value instanceof Date) {
    return value.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }
  return typeof value === 'number' ? formatNumericValue(value) : String(value);
};
