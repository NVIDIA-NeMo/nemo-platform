// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';
import type { TooltipProps } from 'recharts';

interface Props extends TooltipProps<number, string> {
  /** Formats the hovered x value; receives the raw plot value (timestamp for time axes). */
  formatLabel: (value: string | number) => string;
  /** Formats a series value, resolved per series id by the chart. */
  formatValue: (seriesId: string, value: number | null) => string;
}

export const ComparisonTooltip: FC<Props> = ({
  active,
  payload,
  label,
  formatLabel,
  formatValue,
}) => {
  if (!active || !payload?.length) return null;

  return (
    <Stack
      gap="1"
      className="bg-component-tooltip border border-component-tooltip shadow-sm rounded-lg p-3"
    >
      <Text kind="label/semibold/md">{formatLabel(label as string | number)}</Text>
      {payload.map((entry) => (
        <Flex key={String(entry.dataKey)} align="center" gap="2">
          <svg width="12" height="12" aria-hidden focusable="false">
            <rect width="12" height="12" rx="2" fill={entry.color} />
          </svg>
          <Text kind="body/regular/sm" className="text-placeholder">
            {entry.name}
          </Text>
          <Text kind="body/semibold/sm">
            {formatValue(String(entry.dataKey), entry.value ?? null)}
          </Text>
        </Flex>
      ))}
    </Stack>
  );
};
