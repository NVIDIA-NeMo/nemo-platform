// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AXIS_COLOR, AXIS_TEXT_COLOR } from '@nemo/common/src/components/charts/tokens';
import type { LabelProps } from 'recharts';

export const TICK_STYLE = { fontSize: 11, fill: AXIS_TEXT_COLOR } as const;
export const AXIS_LABEL_STYLE = { fontSize: 12, fill: AXIS_TEXT_COLOR } as const;

/** Horizontal rules only — vertical ones fight the series marks. */
export const GRID_PROPS = {
  strokeDasharray: '3 3',
  stroke: AXIS_COLOR,
  strokeOpacity: 0.5,
  vertical: false,
} as const;

/** The hover rule for charts plotted against a continuous x axis. */
export const CURSOR_LINE = { stroke: AXIS_COLOR, strokeWidth: 1 } as const;

/** Axis labels sit outside the plot, so the margin has to grow to make room for them. */
export const chartMargin = (xAxisLabel?: string, yAxisLabel?: string) => ({
  top: 8,
  right: 16,
  bottom: xAxisLabel ? 24 : 0,
  left: yAxisLabel ? 8 : 0,
});

export const xAxisLabelProps = (label?: string): LabelProps | undefined =>
  label
    ? { value: label, position: 'insideBottom', offset: -16, style: AXIS_LABEL_STYLE }
    : undefined;

export const yAxisLabelProps = (label?: string): LabelProps | undefined =>
  label
    ? {
        value: label,
        angle: -90,
        position: 'insideLeft',
        style: { ...AXIS_LABEL_STYLE, textAnchor: 'middle' },
      }
    : undefined;
