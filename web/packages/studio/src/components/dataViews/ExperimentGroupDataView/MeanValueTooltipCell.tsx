// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getTextWithCount } from '@nemo/common/src/utils/formatters';
import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { tooltipClassName } from '@studio/styles/common';
import { type FC, type ReactNode } from 'react';

const aggregateMetricTooltip = (
  label: string,
  count: number | null | undefined,
  runCount: number | null | undefined
): string => {
  // `count` is the number of test cases the mean is taken over; `runCount` is the total attempts. The
  // rollup is test-case-weighted: each test case is averaged over its attempts first, then averaged
  // across test cases (so a test case run k times counts once, not k times).
  const testCases = count ?? 0;
  const attempts = runCount ?? 0;
  // When each test case was attempted once, the test-case-weighted mean is just the plain per-attempt
  // mean, so keep it simple. Otherwise note that each test case's repeats are averaged first.
  if (testCases === attempts) {
    return `Mean ${label} over ${getTextWithCount('test case', testCases)}.`;
  }
  return `Mean ${label} over ${getTextWithCount('test case', testCases)} — each test case averaged over its attempts.`;
};

interface MeanValueTooltipCellProps {
  label: string;
  count: number | null | undefined;
  runCount: number | null | undefined;
  children: ReactNode;
}

export const MeanValueTooltipCell: FC<MeanValueTooltipCellProps> = ({
  label,
  count,
  runCount,
  children,
}) => {
  if (count == null) {
    return <Text>{children}</Text>;
  }
  return (
    <Tooltip
      slotContent={
        <Text kind="body/regular/sm">{aggregateMetricTooltip(label, count, runCount)}</Text>
      }
      className={tooltipClassName}
      side="bottom"
    >
      <Text className="cursor-default border-b border-dotted border-brand">{children}</Text>
    </Tooltip>
  );
};
