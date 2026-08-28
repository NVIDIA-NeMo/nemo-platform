// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import {
  formatTimestamp,
  type TrendMetric,
  type TrendPlotPoint,
} from '@studio/components/charts/ExperimentTrendChart/utils';
import type { FC } from 'react';

interface TrendTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: TrendPlotPoint }>;
  metric: TrendMetric;
}

export const TrendTooltip: FC<TrendTooltipProps> = ({ active, payload, metric }) => {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded border border-base bg-surface p-2 shadow-md">
      <Text kind="body/semibold/sm">{point.name}</Text>
      <div className="mt-1 flex flex-col gap-0.5">
        <Text kind="body/regular/xs">
          {metric.label}: {metric.format(point.y)}
        </Text>
        <Text kind="body/regular/xs" color="subtle">
          {formatTimestamp(point.x)}
        </Text>
      </div>
    </div>
  );
};
