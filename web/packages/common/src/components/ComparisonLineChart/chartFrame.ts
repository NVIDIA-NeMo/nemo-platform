// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AXIS_TEXT_COLOR } from '@nemo/common/src/components/ComparisonLineChart/consts';
import type { LabelProps } from 'recharts';

export const TICK_STYLE = { fontSize: 11, fill: AXIS_TEXT_COLOR } as const;
export const AXIS_LABEL_STYLE = { fontSize: 12, fill: AXIS_TEXT_COLOR } as const;

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
