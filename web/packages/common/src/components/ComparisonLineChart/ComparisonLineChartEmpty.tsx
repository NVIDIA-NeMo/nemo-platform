// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  chartMargin,
  xAxisLabelProps,
  yAxisLabelProps,
} from '@nemo/common/src/components/ComparisonLineChart/chartFrame';
import { AXIS_COLOR } from '@nemo/common/src/components/ComparisonLineChart/consts';
import { Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';
import { CartesianGrid, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';

interface Props {
  message: string;
  height: number;
  xAxisLabel?: string;
  yAxisLabel?: string;
  showGrid?: boolean;
}

/** Two rows are enough to give the axes a domain to draw against. */
const PLACEHOLDER_ROWS = [{ x: 0 }, { x: 1 }];
const PLACEHOLDER_DOMAIN: [number, number] = [0, 1];

/**
 * The chart frame — axes, labels, and grid — with the empty message centered in the plot area.
 * Keeping the frame means the component holds its size and the reader can see what the chart
 * *would* show once data arrives. Tick labels stay off so no scale is implied.
 */
export const ComparisonLineChartEmpty: FC<Props> = ({
  message,
  height,
  xAxisLabel,
  yAxisLabel,
  showGrid = true,
}) => (
  <div className="relative w-full">
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={PLACEHOLDER_ROWS} margin={chartMargin(xAxisLabel, yAxisLabel)}>
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
      </LineChart>
    </ResponsiveContainer>
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <Text kind="body/regular/md" className="text-placeholder">
        {message}
      </Text>
    </div>
  </div>
);
