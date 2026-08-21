// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ChartTooltipRow,
  ChartTooltipSurface,
} from '@nemo/common/src/components/charts/ChartTooltip';
import type { ColoredSeries } from '@nemo/common/src/components/ComparisonLineChart/useComparisonChartModel';
import type { FC } from 'react';
import type { TooltipProps } from 'recharts';

interface Props extends TooltipProps<number, string> {
  /** Visible series, so a dashed one gets the same hollow swatch the legend gives it. */
  series: ColoredSeries[];
  /** Formats the hovered x value; receives the raw plot value (timestamp for time axes). */
  formatLabel: (value: string | number) => string;
  /** Formats a series value, resolved per series id by the chart. */
  formatValue: (seriesId: string, value: number | null) => string;
}

export const ComparisonTooltip: FC<Props> = ({
  active,
  payload,
  label,
  series,
  formatLabel,
  formatValue,
}) => {
  if (!active || !payload?.length) return null;

  return (
    <ChartTooltipSurface label={formatLabel(label as string | number)}>
      {payload.map((entry) => (
        <ChartTooltipRow
          key={String(entry.dataKey)}
          color={entry.color}
          dashed={series.find((s) => s.id === String(entry.dataKey))?.dashed}
          label={entry.name}
          value={formatValue(String(entry.dataKey), entry.value ?? null)}
        />
      ))}
    </ChartTooltipSurface>
  );
};
