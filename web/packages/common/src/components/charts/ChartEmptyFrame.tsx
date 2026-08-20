// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  GRID_PROPS,
  chartMargin,
  xAxisLabelProps,
  yAxisLabelProps,
} from '@nemo/common/src/components/charts/frame';
import { AXIS_COLOR } from '@nemo/common/src/components/charts/tokens';
import { Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';
import { CartesianGrid, type LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';

interface Props {
  message: string;
  height: number;
  xAxisLabel?: string;
  yAxisLabel?: string;
  showGrid?: boolean;
  /**
   * The chart element the caller's real plot uses. `LineChart` and `ComposedChart` happen to
   * render this frame identically today, but that rests on recharts internals — do not inline one.
   */
  chart: typeof LineChart;
}

/** Two rows are enough to give the axes a domain to draw against. */
const PLACEHOLDER_ROWS = [{ x: 0 }, { x: 1 }];
const PLACEHOLDER_DOMAIN: [number, number] = [0, 1];

/**
 * Axes and grid with the message centered, so the component holds its size and shows what the
 * chart *would* look like. Tick labels stay off so no scale is implied.
 */
export const ChartEmptyFrame: FC<Props> = ({
  chart: Chart,
  message,
  height,
  xAxisLabel,
  yAxisLabel,
  showGrid = true,
}) => (
  <div className="relative w-full">
    <ResponsiveContainer width="100%" height={height}>
      <Chart data={PLACEHOLDER_ROWS} margin={chartMargin(xAxisLabel, yAxisLabel)}>
        {showGrid && <CartesianGrid {...GRID_PROPS} />}
        <XAxis
          dataKey="x"
          type="number"
          domain={PLACEHOLDER_DOMAIN}
          tick={false}
          stroke={AXIS_COLOR}
          label={xAxisLabelProps(xAxisLabel)}
        />
        <YAxis
          domain={PLACEHOLDER_DOMAIN}
          tick={false}
          stroke={AXIS_COLOR}
          label={yAxisLabelProps(yAxisLabel)}
        />
      </Chart>
    </ResponsiveContainer>
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <Text kind="body/regular/md" className="text-placeholder">
        {message}
      </Text>
    </div>
  </div>
);
