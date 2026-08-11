// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ComparisonAnnotationLabel } from '@nemo/common/src/components/ComparisonLineChart/ComparisonAnnotationLabel';
import { ComparisonLegend } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLegend';
import { ComparisonLineChartEmpty } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLineChartEmpty';
import { ComparisonLineChartSkeleton } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLineChartSkeleton';
import { ComparisonTooltip } from '@nemo/common/src/components/ComparisonLineChart/ComparisonTooltip';
import {
  ANNOTATION_COLOR,
  AXIS_COLOR,
  AXIS_TEXT_COLOR,
  DEFAULT_CHART_HEIGHT,
  FADED_SERIES_OPACITY,
  REFERENCE_LINE_COLOR,
} from '@nemo/common/src/components/ComparisonLineChart/consts';
import type { ComparisonLineChartProps } from '@nemo/common/src/components/ComparisonLineChart/types';
import {
  buildChartRows,
  formatNumericValue,
  formatXValueDefault,
  hasPlottableData,
  inferXAxisType,
  resolveAnnotation,
  seriesColor,
} from '@nemo/common/src/components/ComparisonLineChart/utils';
import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { useCallback, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export * from '@nemo/common/src/components/ComparisonLineChart/consts';
export * from '@nemo/common/src/components/ComparisonLineChart/types';
export * from '@nemo/common/src/components/ComparisonLineChart/utils';

const TICK_STYLE = { fontSize: 11, fill: AXIS_TEXT_COLOR } as const;
const AXIS_LABEL_STYLE = { fontSize: 12, fill: AXIS_TEXT_COLOR } as const;

/**
 * Multi-series line chart for comparing runs, models, or variants over a shared x axis.
 * Series are colored from the shared palette, the legend toggles them on and off, and hovering a
 * legend entry fades the others so a single line can be read out of a crowded chart.
 */
export const ComparisonLineChart = ({
  series,
  xAxis,
  xAxisLabel,
  yAxisLabel,
  xAxisType,
  yAxisMin,
  yAxisMax,
  height = DEFAULT_CHART_HEIGHT,
  curve = 'monotone',
  showGrid = true,
  showLegend = true,
  legendPosition = 'top',
  title,
  legendInteractive = true,
  showMarks,
  referenceLines,
  annotations,
  formatXValue = formatXValueDefault,
  formatYValue = formatNumericValue,
  loading = false,
  emptyMessage = 'No data to compare',
  initialHiddenSeriesIds,
  onVisibleSeriesChange,
  className,
}: ComparisonLineChartProps) => {
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(
    () => new Set(initialHiddenSeriesIds ?? [])
  );
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const colored = useMemo(
    () => series.map((entry, index) => ({ ...entry, resolvedColor: seriesColor(entry, index) })),
    [series]
  );

  const rows = useMemo(() => buildChartRows(series, xAxis), [series, xAxis]);
  const resolvedAnnotations = useMemo(
    () =>
      (annotations ?? [])
        .map((annotation) => resolveAnnotation(annotation, series, xAxis))
        .filter((annotation) => annotation !== null),
    [annotations, series, xAxis]
  );
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

  const legendItems = colored.map((entry) => ({
    id: entry.id,
    label: entry.label,
    color: entry.resolvedColor,
    dashed: entry.dashed,
    hidden: hiddenIds.has(entry.id),
  }));

  const renderLegend = (interactive: boolean) => (
    <ComparisonLegend
      items={legendItems}
      interactive={interactive}
      justify={legendPosition === 'top' ? 'end' : 'center'}
      onToggle={interactive ? toggleSeries : undefined}
      onHover={interactive ? setHoveredId : undefined}
    />
  );

  const showTopLegend = showLegend && legendPosition === 'top' && series.length > 0;

  /** Title on the left, legend on the right; renders when either is present. */
  const renderHeader = (interactive: boolean) =>
    title || showTopLegend ? (
      <Flex justify={title ? 'between' : 'end'} align="center" gap="density-md" className="pb-2">
        {title && <Text kind="label/bold/lg">{title}</Text>}
        {showTopLegend && renderLegend(interactive)}
      </Flex>
    ) : null;

  if (loading) {
    return <ComparisonLineChartSkeleton height={height} />;
  }

  if (!hasPlottableData(series, xAxis)) {
    return (
      <Stack className={className}>
        {renderHeader(false)}
        <ComparisonLineChartEmpty
          message={emptyMessage}
          height={height}
          xAxisLabel={xAxisLabel}
          yAxisLabel={yAxisLabel}
          showGrid={showGrid}
        />
        {showLegend && legendPosition === 'bottom' && series.length > 0 && renderLegend(false)}
      </Stack>
    );
  }

  return (
    <Stack className={className}>
      {renderHeader(legendInteractive)}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          className="[&_.recharts-surface]:overflow-visible"
          data={rows}
          margin={{ top: 8, right: 16, bottom: xAxisLabel ? 24 : 0, left: yAxisLabel ? 8 : 0 }}
        >
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={AXIS_COLOR}
              strokeOpacity={0.5}
              vertical={false}
            />
          )}
          <XAxis
            dataKey="x"
            type={resolvedXAxisType === 'category' ? 'category' : 'number'}
            scale={isTimeAxis ? 'time' : 'auto'}
            domain={resolvedXAxisType === 'category' ? undefined : ['dataMin', 'dataMax']}
            tickFormatter={formatPlotValue}
            tick={TICK_STYLE}
            stroke={AXIS_COLOR}
            label={
              xAxisLabel
                ? {
                    value: xAxisLabel,
                    position: 'insideBottom',
                    offset: -16,
                    style: AXIS_LABEL_STYLE,
                  }
                : undefined
            }
          />
          <YAxis
            domain={[yAxisMin ?? 'auto', yAxisMax ?? 'auto']}
            tickFormatter={formatYValue}
            tick={TICK_STYLE}
            stroke={AXIS_COLOR}
            label={
              yAxisLabel
                ? {
                    value: yAxisLabel,
                    angle: -90,
                    position: 'insideLeft',
                    style: { ...AXIS_LABEL_STYLE, textAnchor: 'middle' },
                  }
                : undefined
            }
          />
          <Tooltip
            cursor={{ stroke: AXIS_COLOR, strokeWidth: 1 }}
            content={
              <ComparisonTooltip formatLabel={formatPlotValue} formatValue={formatSeriesValue} />
            }
          />
          {referenceLines?.map((line) => (
            <ReferenceLine
              key={`ref-${line.y}-${line.label ?? ''}`}
              y={line.y}
              stroke={line.color ?? REFERENCE_LINE_COLOR}
              strokeDasharray="4 4"
              label={
                line.label
                  ? { value: line.label, position: 'insideTopRight', style: TICK_STYLE }
                  : undefined
              }
            />
          ))}
          {resolvedAnnotations.map((annotation) => (
            <ReferenceLine
              key={`annotation-${annotation.x}-${annotation.label}`}
              segment={[
                { x: annotation.x, y: annotation.fromY },
                { x: annotation.x, y: annotation.toY },
              ]}
              stroke={annotation.color ?? ANNOTATION_COLOR}
              strokeDasharray="4 4"
              ifOverflow="extendDomain"
              label={
                <ComparisonAnnotationLabel
                  label={annotation.label}
                  description={annotation.description}
                  color={annotation.color}
                  pointsUp={annotation.pointsUp}
                  labelSide={annotation.labelSide}
                />
              }
            />
          ))}
          {colored
            .filter((entry) => !hiddenIds.has(entry.id))
            .map((entry) => (
              <Line
                key={entry.id}
                type={curve}
                dataKey={entry.id}
                name={entry.label}
                stroke={entry.resolvedColor}
                strokeWidth={2}
                strokeDasharray={entry.dashed ? '6 4' : undefined}
                strokeOpacity={hoveredId && hoveredId !== entry.id ? FADED_SERIES_OPACITY : 1}
                dot={showMarks ?? entry.data.length <= 3}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
        </LineChart>
      </ResponsiveContainer>
      {showLegend && legendPosition === 'bottom' && (
        <div className="pt-2">{renderLegend(legendInteractive)}</div>
      )}
    </Stack>
  );
};
