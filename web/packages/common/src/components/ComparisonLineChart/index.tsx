// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ChartEmptyFrame } from '@nemo/common/src/components/charts/ChartEmptyFrame';
import { ChartHeader } from '@nemo/common/src/components/charts/ChartHeader';
import { ChartLegend } from '@nemo/common/src/components/charts/ChartLegend';
import { ChartSkeleton } from '@nemo/common/src/components/charts/ChartSkeleton';
import {
  CURSOR_LINE,
  GRID_PROPS,
  TICK_STYLE,
  chartMargin,
  xAxisLabelProps,
  yAxisLabelProps,
} from '@nemo/common/src/components/charts/frame';
import { renderReferenceLines } from '@nemo/common/src/components/charts/referenceLines';
import { AXIS_COLOR, DEFAULT_CHART_HEIGHT } from '@nemo/common/src/components/charts/tokens';
import {
  renderAnnotations,
  renderSeriesLines,
} from '@nemo/common/src/components/ComparisonLineChart/chartLayers';
import { ComparisonTooltip } from '@nemo/common/src/components/ComparisonLineChart/ComparisonTooltip';
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
    <ChartLegend
      items={model.legendItems}
      interactive={interactive}
      justify={legendPosition === 'top' ? 'end' : 'center'}
      onToggle={interactive ? model.toggleSeries : undefined}
      onHover={interactive ? model.setHoveredId : undefined}
    />
  );

  const hasLegend = showLegend && series.length > 0;
  const renderHeader = (interactive: boolean) => (
    <ChartHeader
      title={title}
      legend={hasLegend && legendPosition === 'top' ? renderLegend(interactive) : undefined}
    />
  );
  const showBottomLegend = hasLegend && legendPosition === 'bottom';

  if (loading) {
    return <ChartSkeleton height={height} testId="comparison-line-chart-skeleton" />;
  }

  if (!hasPlottableData(series, xAxis)) {
    return (
      <Stack className={className}>
        {renderHeader(false)}
        <ChartEmptyFrame
          chart={LineChart}
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
          {showGrid && <CartesianGrid {...GRID_PROPS} />}
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
            cursor={CURSOR_LINE}
            content={
              <ComparisonTooltip
                series={model.visibleSeries}
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
