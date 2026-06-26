// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { tooltipClassName } from '@studio/styles/common';
import { type FC, type ReactNode } from 'react';

/**
 * Builds the hover explanation for an aggregated metric cell — which statistic is shown, over how
 * many runs it was computed (N), and how many runs exist in total (M). N is the metric's own
 * `count` (how many runs contributed a value); M is the experiment's `run_count`. The shape is
 * identical for every evaluator and for cost/latency, so the only per-metric inputs are the label
 * and the run noun — nothing producer-specific.
 *
 * @example "Mean Accuracy over 8 scored runs (of 10 total)."
 */
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
  /** Human-readable metric name, e.g. an evaluator title or "cost". */
  label: string;
  /** Singular noun for one contributing run — "scored run" for evaluators, "run" for cost/latency. */
  runNoun: string;
  /** How many runs contributed a value to this metric's aggregate (N). */
  count: number | null | undefined;
  /** Total runs in the experiment (M). */
  runCount: number | null | undefined;
  /** The formatted metric value to display. */
  children: ReactNode;
}

/**
 * A metric value with a hover tooltip explaining how it was aggregated and over how many runs. The
 * dotted underline marks the value as hoverable, matching the Name column's affordance.
 */
export const MeanValueTooltipCell: FC<MeanValueTooltipCellProps> = ({
  label,
  runNoun,
  count,
  runCount,
  children,
}) => (
  <Tooltip
    slotContent={
      <Text kind="body/regular/sm">{aggregateMetricTooltip(label, runNoun, count, runCount)}</Text>
    }
    className={tooltipClassName}
    side="bottom"
  >
    <Text className="cursor-default border-b border-dotted border-brand">{children}</Text>
  </Tooltip>
);
