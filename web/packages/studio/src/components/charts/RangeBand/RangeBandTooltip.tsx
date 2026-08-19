// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ChartTooltipRow,
  ChartTooltipSurface,
} from '@nemo/common/src/components/charts/ChartTooltip';
import { Stack, Text } from '@nvidia/foundations-react-core';
import type { ColoredBandSeries } from '@studio/components/charts/RangeBand/types';
import { lowerKeyFor, upperKeyFor } from '@studio/components/charts/RangeBand/utils';
import type { FC } from 'react';
import type { TooltipProps } from 'recharts';

interface Props extends TooltipProps<number, string> {
  series: ColoredBandSeries[];
  /** Formats the hovered x value; receives the raw plot value (timestamp for time axes). */
  formatLabel: (value: string | number) => string;
  /** Formats a series value, resolved per series id by the chart. */
  formatValue: (seriesId: string, value: number | null) => string;
}

const numericOrNull = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/**
 * Reads the hovered row directly rather than recharts' per-item payload: a band's `dataKey` is an
 * accessor, so its payload entry carries no id to resolve a label or formatter against.
 */
export const RangeBandTooltip: FC<Props> = ({
  active,
  payload,
  label,
  series,
  formatLabel,
  formatValue,
}) => {
  const row = payload?.[0]?.payload as Record<string, unknown> | undefined;
  if (!active || !row) return null;

  const entries = series
    .map((entry) => ({
      id: entry.id,
      label: entry.label,
      color: entry.resolvedColor,
      dashed: entry.dashed,
      center: numericOrNull(row[entry.id]),
      lower: numericOrNull(row[lowerKeyFor(entry.id)]),
      upper: numericOrNull(row[upperKeyFor(entry.id)]),
    }))
    .filter((entry) => entry.center !== null || (entry.lower !== null && entry.upper !== null));

  if (entries.length === 0) return null;

  return (
    <ChartTooltipSurface label={formatLabel(label as string | number)}>
      {entries.map((entry) => (
        <Stack key={entry.id} gap="1">
          <ChartTooltipRow
            color={entry.color}
            dashed={entry.dashed}
            label={entry.label}
            value={entry.center !== null ? formatValue(entry.id, entry.center) : undefined}
          />
          {entry.lower !== null && entry.upper !== null && (
            <Text kind="body/regular/sm" className="text-placeholder pl-5">
              {formatValue(entry.id, entry.lower)} – {formatValue(entry.id, entry.upper)}
            </Text>
          )}
        </Stack>
      ))}
    </ChartTooltipSurface>
  );
};
