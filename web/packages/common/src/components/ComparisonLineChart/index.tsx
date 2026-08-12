// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  TICK_STYLE,
  chartMargin,
  xAxisLabelProps,
  yAxisLabelProps,
} from '@nemo/common/src/components/ComparisonLineChart/chartFrame';
import {
  renderAnnotations,
  renderReferenceLines,
  renderSeriesLines,
} from '@nemo/common/src/components/ComparisonLineChart/chartLayers';
import { ComparisonChartHeader } from '@nemo/common/src/components/ComparisonLineChart/ComparisonChartHeader';
import { ComparisonLegend } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLegend';
import { ComparisonLineChartEmpty } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLineChartEmpty';
import { ComparisonLineChartSkeleton } from '@nemo/common/src/components/ComparisonLineChart/ComparisonLineChartSkeleton';
import { ComparisonTooltip } from '@nemo/common/src/components/ComparisonLineChart/ComparisonTooltip';
import {
  AXIS_COLOR,
  DEFAULT_CHART_HEIGHT,
} from '@nemo/common/src/components/ComparisonLineChart/consts';
import type { ComparisonLineChartProps } from '@nemo/common/src/components/ComparisonLineChart/types';
import { useComparisonChartModel } from '@nemo/common/src/components/ComparisonLineChart/useComparisonChartModel';
import { hasPlottableData } from '@nemo/common/src/components/ComparisonLineChart/utils';
import { Stack } from '@nvidia/foundations-react-core';
import { CartesianGrid, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export * from '@nemo/common/src/components/ComparisonLineChart/consts';
export * from '@nemo/common/src/components/ComparisonLineChart/types';
export * from '@nemo/common/src/components/ComparisonLineChart/utils';

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
  formatXValue,
  formatYValue,
  loading = false,
  emptyMessage = 'No data to compare',
  initialHiddenSeriesIds,
  onVisibleSeriesChange,
  className,
}: ComparisonLineChartProps) => {
  const model = useComparisonChartModel({
    series,
    xAxis,
    xAxisType,
    annotations,
    formatXValue,
    formatYValue,
    initialHiddenSeriesIds,
    onVisibleSeriesChange,
  });

  const renderLegend = (interactive: boolean) => (
    <ComparisonLegend
      items={model.legendItems}
      interactive={interactive}
      justify={legendPosition === 'top' ? 'end' : 'center'}
      onToggle={interactive ? model.toggleSeries : undefined}
      onHover={interactive ? model.setHoveredId : undefined}
    />
  );

  const hasLegend = showLegend && series.length > 0;
  const renderHeader = (interactive: boolean) => (
    <ComparisonChartHeader
      title={title}
      legend={hasLegend && legendPosition === 'top' ? renderLegend(interactive) : undefined}
    />
  );
  const showBottomLegend = hasLegend && legendPosition === 'bottom';

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
        {showBottomLegend && renderLegend(false)}
      </Stack>
    );
  }

  return (
    <Stack className={className}>
      {renderHeader(legendInteractive)}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          className="[&_.recharts-surface]:overflow-visible"
          data={model.rows}
          margin={chartMargin(xAxisLabel, yAxisLabel)}
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
            type={model.resolvedXAxisType === 'category' ? 'category' : 'number'}
            scale={model.isTimeAxis ? 'time' : 'auto'}
            domain={model.resolvedXAxisType === 'category' ? undefined : ['dataMin', 'dataMax']}
            tickFormatter={model.formatPlotValue}
            tick={TICK_STYLE}
            stroke={AXIS_COLOR}
            label={xAxisLabelProps(xAxisLabel)}
          />
          <YAxis
            domain={[yAxisMin ?? 'auto', yAxisMax ?? 'auto']}
            tickFormatter={model.formatYValue}
            tick={TICK_STYLE}
            stroke={AXIS_COLOR}
            label={yAxisLabelProps(yAxisLabel)}
          />
          <Tooltip
            cursor={{ stroke: AXIS_COLOR, strokeWidth: 1 }}
            content={
              <ComparisonTooltip
                formatLabel={model.formatPlotValue}
                formatValue={model.formatSeriesValue}
              />
            }
          />
          {renderReferenceLines(referenceLines)}
          {renderAnnotations(model.resolvedAnnotations)}
          {renderSeriesLines(model.visibleSeries, {
            curve,
            hoveredId: model.hoveredId,
            showMarks,
          })}
        </LineChart>
      </ResponsiveContainer>
      {showBottomLegend && <div className="pt-2">{renderLegend(legendInteractive)}</div>}
    </Stack>
  );
};
