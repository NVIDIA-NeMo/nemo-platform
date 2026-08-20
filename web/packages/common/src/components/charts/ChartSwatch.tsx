// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FC } from 'react';

const SIZE = 10;
const RADIUS = 4;

/**
 * The dot standing in for a series, shared by the legend and the tooltip so one series reads the
 * same in both. Dashed series get a hollow dot, matching how their line is drawn.
 */
export const ChartSwatch: FC<{ color?: string; dashed?: boolean }> = ({ color, dashed }) => (
  <svg width={SIZE} height={SIZE} aria-hidden focusable="false">
    <circle
      cx={SIZE / 2}
      cy={SIZE / 2}
      r={dashed ? RADIUS - 0.75 : RADIUS}
      fill={dashed ? 'none' : color}
      stroke={dashed ? color : 'none'}
      strokeWidth={dashed ? 1.5 : 0}
    />
  </svg>
);
