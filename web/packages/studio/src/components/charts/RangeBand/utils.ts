// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { toPlotValue } from '@nemo/common/src/components/charts/format';
import type { ChartXValue } from '@nemo/common/src/components/charts/types';
import type { RangeBandSeries } from '@studio/components/charts/RangeBand/types';

/** A recharts row: the shared x value, plus a center and two bounds per series. */
export interface RangeBandChartRow {
  x: string | number;
  [key: string]: string | number | null;
}

/**
 * Bound keys, kept clear of the bare series id that carries the center line. Reserved rather than
 * collision-proof — a series named `foo__lower` would clash, so `buildRangeBandRows` rejects it.
 */
const LOWER_SUFFIX = '__lower';
const UPPER_SUFFIX = '__upper';

export const lowerKeyFor = (seriesId: string): string => `${seriesId}${LOWER_SUFFIX}`;
export const upperKeyFor = (seriesId: string): string => `${seriesId}${UPPER_SUFFIX}`;

const finiteOrNull = (value: number | null | undefined): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/**
 * Pivots the parallel `series[]` arrays into the row-per-x-value shape recharts expects. Series
 * are keyed by id, so ids must not collide with the reserved `x` key or the bound suffixes.
 */
export const buildRangeBandRows = (
  series: RangeBandSeries[],
  xAxis: ChartXValue[]
): RangeBandChartRow[] => {
  const ids = new Set<string>();
  for (const { id } of series) {
    if (id === 'x') throw new Error('Series id "x" is reserved for the x axis.');
    if (id.endsWith(LOWER_SUFFIX) || id.endsWith(UPPER_SUFFIX)) {
      throw new Error(`Series id "${id}" ends with a reserved band-bound suffix.`);
    }
    if (ids.has(id)) throw new Error(`Duplicate series id: ${id}`);
    ids.add(id);
  }

  return xAxis.map((xValue, index) => {
    const row: RangeBandChartRow = { x: toPlotValue(xValue) };
    for (const entry of series) {
      row[entry.id] = finiteOrNull(entry.data?.[index]);
      row[lowerKeyFor(entry.id)] = finiteOrNull(entry.lower[index]);
      row[upperKeyFor(entry.id)] = finiteOrNull(entry.upper[index]);
    }
    return row;
  });
};

/** True when at least one series has a finite bound or center value to draw. */
export const hasPlottableBands = (series: RangeBandSeries[], xAxis: ChartXValue[]): boolean =>
  xAxis.length > 0 &&
  series.some((entry) =>
    [entry.data ?? [], entry.lower, entry.upper].some((values) =>
      values.slice(0, xAxis.length).some((value) => finiteOrNull(value) !== null)
    )
  );

export const hasCenterLine = (series: RangeBandSeries): boolean =>
  (series.data ?? []).some((value) => finiteOrNull(value) !== null);
