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
import { Stack } from '@nvidia/foundations-react-core';
import { renderBands, renderSeriesLines } from '@studio/components/charts/RangeBand/chartLayers';
import { DEFAULT_BAND_OPACITY } from '@studio/components/charts/RangeBand/consts';
import { RangeBandTooltip } from '@studio/components/charts/RangeBand/RangeBandTooltip';
import type { RangeBandProps } from '@studio/components/charts/RangeBand/types';
import { useRangeBandChartModel } from '@studio/components/charts/RangeBand/useRangeBandChartModel';
import { hasPlottableBands } from '@studio/components/charts/RangeBand/utils';
import { CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

/**
 * Multi-series band chart: a shaded envelope per series, optionally with a center line. The line
 * comes from `data` alone — see the "Line off-center in the band" story.
 */
export const RangeBand = ({
  series,
  xAxis,
  xAxisLabel,
  yAxisLabel,
  xAxisType,
  yAxisMin,
  yAxisMax,
  height = DEFAULT_CHART_HEIGHT,
  curve = 'monotone',
  bandOpacity = DEFAULT_BAND_OPACITY,
  showGrid = true,
  showLegend = true,
  legendPosition = 'top',
  title,
  legendInteractive = true,
  showMarks,
  referenceLines,
  formatXValue,
  formatYValue,
  loading = false,
  emptyMessage = 'No data to compare',
  initialHiddenSeriesIds,
  onVisibleSeriesChange,
  className,
}: RangeBandProps) => {
  const model = useRangeBandChartModel({
    series,
    xAxis,
    xAxisType,
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
    return <ChartSkeleton height={height} testId="range-band-skeleton" />;
  }

  if (!hasPlottableBands(series, xAxis)) {
    return (
      <Stack className={className}>
        {renderHeader(false)}
        <ChartEmptyFrame
          chart={ComposedChart}
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
        <ComposedChart
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
              <RangeBandTooltip
                series={model.visibleSeries}
                formatLabel={model.formatPlotValue}
                formatValue={model.formatSeriesValue}
              />
            }
          />
          {/* Bands first so the center lines draw on top of them. */}
          {renderBands(model.visibleSeries, {
            type: curve,
            hoveredId: model.hoveredId,
            bandOpacity,
          })}
          {renderReferenceLines(referenceLines)}
          {renderSeriesLines(model.visibleSeries, {
            curve,
            hoveredId: model.hoveredId,
            showMarks,
          })}
        </ComposedChart>
      </ResponsiveContainer>
      {showBottomLegend && <div className="pt-2">{renderLegend(legendInteractive)}</div>}
    </Stack>
  );
};
