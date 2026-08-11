// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { COMPARISON_SERIES_COLORS } from '@nemo/common/src/components/ComparisonLineChart/consts';
import type {
  ComparisonAnnotation,
  ComparisonSeries,
  ComparisonXAxisType,
  ComparisonXValue,
} from '@nemo/common/src/components/ComparisonLineChart/types';

/** A recharts row: the shared x value plus one entry per series, keyed by series id. */
export interface ComparisonChartRow {
  x: string | number;
  [seriesId: string]: string | number | null;
}

export const seriesColor = (series: ComparisonSeries, index: number): string =>
  series.color ?? COMPARISON_SERIES_COLORS[index % COMPARISON_SERIES_COLORS.length];

export const inferXAxisType = (xAxis: ComparisonXValue[]): ComparisonXAxisType => {
  const first = xAxis.find((value) => value !== undefined && value !== null);
  if (first instanceof Date) return 'time';
  if (typeof first === 'number') return 'number';
  return 'category';
};

/** Dates become timestamps so recharts can place them on a numeric axis. */
export const toPlotValue = (value: ComparisonXValue): string | number =>
  value instanceof Date ? value.getTime() : value;

/**
 * Pivots the parallel `series[].data` arrays into the row-per-x-value shape recharts expects.
 * Series are keyed by id, so ids must not collide with the reserved `x` key.
 */
export const buildChartRows = (
  series: ComparisonSeries[],
  xAxis: ComparisonXValue[]
): ComparisonChartRow[] => {
  const ids = new Set<string>();
  for (const { id } of series) {
    if (id === 'x') throw new Error('Series id "x" is reserved for the x axis.');
    if (ids.has(id)) throw new Error(`Duplicate series id: ${id}`);
    ids.add(id);
  }

  return xAxis.map((xValue, index) => {
    const row: ComparisonChartRow = { x: toPlotValue(xValue) };
    for (const entry of series) {
      const value = entry.data[index];
      row[entry.id] = typeof value === 'number' && Number.isFinite(value) ? value : null;
    }
    return row;
  });
};

export interface ResolvedAnnotation {
  x: string | number;
  fromY: number;
  toY: number;
  label: string;
  description?: string;
  color?: string;
  /** The arrow points up the y axis, so the head sits at the top of the segment. */
  pointsUp: boolean;
  labelSide: 'left' | 'right';
}

/** How far along the x axis a point sits, 0 at the left edge and 1 at the right. */
const axisFraction = (xAxis: ComparisonXValue[], index: number, plotX: string | number): number => {
  const plotted = xAxis.map(toPlotValue);
  const numeric = plotted.filter((value): value is number => typeof value === 'number');
  if (typeof plotX === 'number' && numeric.length === plotted.length && numeric.length > 1) {
    const min = Math.min(...numeric);
    const max = Math.max(...numeric);
    return max === min ? 0 : (plotX - min) / (max - min);
  }
  return plotted.length > 1 ? index / (plotted.length - 1) : 0;
};

/** Past this point the callout text would run off the right edge, so it flips to the other side. */
const LABEL_FLIP_FRACTION = 0.65;

const ratioLabel = (fromY: number, toY: number): string => {
  const [low, high] = [Math.abs(fromY), Math.abs(toY)].sort((a, b) => a - b);
  if (low === 0 || !Number.isFinite(high / low)) return '';
  const ratio = high / low;
  return `${ratio >= 10 ? Math.round(ratio) : ratio.toFixed(1)}X`;
};

/**
 * Resolves an annotation's endpoints against the data, looking up the two named series at `x`.
 * Returns `null` when the x value or either endpoint is missing, so a callout silently drops
 * rather than rendering at a bogus position.
 */
export const resolveAnnotation = (
  annotation: ComparisonAnnotation,
  series: ComparisonSeries[],
  xAxis: ComparisonXValue[]
): ResolvedAnnotation | null => {
  const plotX = toPlotValue(annotation.x);
  const index = xAxis.findIndex((value) => toPlotValue(value) === plotX);
  if (index === -1) return null;

  const valueAt = (seriesId: string): number | undefined => {
    const value = series.find((s) => s.id === seriesId)?.data[index];
    return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
  };

  const [fromId, toId] = annotation.betweenSeriesIds ?? [];
  const fromY = fromId ? valueAt(fromId) : annotation.fromY;
  const toY = toId ? valueAt(toId) : annotation.toY;
  if (fromY === undefined || toY === undefined) return null;

  return {
    x: plotX,
    fromY,
    toY,
    label: annotation.label ?? ratioLabel(fromY, toY),
    description: annotation.description,
    color: annotation.color,
    pointsUp: toY > fromY,
    labelSide:
      annotation.labelSide ??
      (axisFraction(xAxis, index, plotX) > LABEL_FLIP_FRACTION ? 'left' : 'right'),
  };
};

/** True when at least one series has a finite value to draw; an all-null chart reads as empty. */
export const hasPlottableData = (series: ComparisonSeries[], xAxis: ComparisonXValue[]): boolean =>
  xAxis.length > 0 &&
  series.some((s) =>
    s.data
      .slice(0, xAxis.length)
      .some((value) => typeof value === 'number' && Number.isFinite(value))
  );

/** Compacts large magnitudes (16000 -> "16K") while keeping small values precise. */
export const formatNumericValue = (value: number): string =>
  Math.abs(value) >= 1000
    ? value.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })
    : value.toLocaleString(undefined, { maximumFractionDigits: 3 });

export const formatXValueDefault = (value: ComparisonXValue): string => {
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
