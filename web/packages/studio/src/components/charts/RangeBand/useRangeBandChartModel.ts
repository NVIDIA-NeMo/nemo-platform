// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  formatNumericValue,
  formatXValueDefault,
  inferXAxisType,
  seriesColor,
} from '@nemo/common/src/components/charts/format';
import type { ChartLegendItem } from '@nemo/common/src/components/charts/types';
import type { ColoredBandSeries, RangeBandProps } from '@studio/components/charts/RangeBand/types';
import { buildRangeBandRows } from '@studio/components/charts/RangeBand/utils';
import { useCallback, useMemo, useState } from 'react';

type ModelOptions = Pick<
  RangeBandProps,
  | 'series'
  | 'xAxis'
  | 'xAxisType'
  | 'formatXValue'
  | 'formatYValue'
  | 'initialHiddenSeriesIds'
  | 'onVisibleSeriesChange'
>;

/**
 * Derives everything the chart draws from its props: pivoted rows and resolved colors, plus the
 * legend visibility/hover state the chart and legend share.
 */
export const useRangeBandChartModel = ({
  series,
  xAxis,
  xAxisType,
  formatXValue = formatXValueDefault,
  formatYValue = formatNumericValue,
  initialHiddenSeriesIds,
  onVisibleSeriesChange,
}: ModelOptions) => {
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(
    () => new Set(initialHiddenSeriesIds ?? [])
  );
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const colored = useMemo<ColoredBandSeries[]>(
    () => series.map((entry, index) => ({ ...entry, resolvedColor: seriesColor(entry, index) })),
    [series]
  );

  const rows = useMemo(() => buildRangeBandRows(series, xAxis), [series, xAxis]);

  const resolvedXAxisType = xAxisType ?? inferXAxisType(xAxis);
  const isTimeAxis = resolvedXAxisType === 'time';

  const toggleSeries = useCallback(
    (id: string) => {
      const next = new Set(hiddenIds);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      setHiddenIds(next);
      onVisibleSeriesChange?.(series.filter((s) => !next.has(s.id)).map((s) => s.id));
    },
    [hiddenIds, onVisibleSeriesChange, series]
  );

  /** Time axes plot timestamps, so restore the `Date` before handing values to the formatter. */
  const formatPlotValue = useCallback(
    (value: string | number) => formatXValue(isTimeAxis ? new Date(value) : value),
    [formatXValue, isTimeAxis]
  );

  const formatSeriesValue = useCallback(
    (seriesId: string, value: number | null) => {
      const entry = series.find((s) => s.id === seriesId);
      return entry?.valueFormatter?.(value) ?? (value === null ? '—' : formatYValue(value));
    },
    [series, formatYValue]
  );

  const legendItems = useMemo<ChartLegendItem[]>(
    () =>
      colored.map((entry) => ({
        id: entry.id,
        label: entry.label,
        color: entry.resolvedColor,
        dashed: entry.dashed,
        hidden: hiddenIds.has(entry.id),
      })),
    [colored, hiddenIds]
  );

  const visibleSeries = useMemo(
    () => colored.filter((entry) => !hiddenIds.has(entry.id)),
    [colored, hiddenIds]
  );

  return {
    rows,
    resolvedXAxisType,
    isTimeAxis,
    hoveredId,
    setHoveredId,
    toggleSeries,
    formatPlotValue,
    formatSeriesValue,
    formatYValue,
    legendItems,
    visibleSeries,
  };
};
