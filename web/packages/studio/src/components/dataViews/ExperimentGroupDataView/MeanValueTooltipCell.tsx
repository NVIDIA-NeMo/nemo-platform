// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { tooltipClassName } from '@studio/styles/common';
import { type FC, type ReactNode } from 'react';

const aggregateMetricTooltip = (
  label: string,
  runNoun: string,
  count: number | null | undefined,
  runCount: number | null | undefined
): string => {
  const contributing = count ?? 0;
  const total = runCount ?? 0;
  const noun = contributing === 1 ? runNoun : `${runNoun}s`;
  return `Mean ${label} over ${contributing} ${noun} (of ${total} total).`;
};

interface MeanValueTooltipCellProps {
  label: string;
  runNoun: string;
  count: number | null | undefined;
  runCount: number | null | undefined;
  children: ReactNode;
}

export const MeanValueTooltipCell: FC<MeanValueTooltipCellProps> = ({
  label,
  runNoun,
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
        <Text kind="body/regular/sm">
          {aggregateMetricTooltip(label, runNoun, count, runCount)}
        </Text>
      }
      className={tooltipClassName}
      side="bottom"
    >
      <Text className="cursor-default border-b border-dotted border-brand">{children}</Text>
    </Tooltip>
  );
};
