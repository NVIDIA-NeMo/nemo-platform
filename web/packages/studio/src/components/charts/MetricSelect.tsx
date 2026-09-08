// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import type { FC } from 'react';

/** The least a chart's metric has to expose to be selectable. Both the Pareto metrics and the
 * over-time metrics satisfy it, so the two charts share one selector. */
export interface SelectableMetric {
  readonly id: string;
  readonly label: string;
}

interface MetricSelectProps {
  label: string;
  value: string;
  metrics: readonly SelectableMetric[];
  onChange: (id: string) => void;
  /** Widens the trigger for longer metric names; the axis pickers stay compact. */
  triggerClassName?: string;
}

export const MetricSelect: FC<MetricSelectProps> = ({
  label,
  value,
  metrics,
  onChange,
  triggerClassName = 'w-26',
}) => (
  <label className="flex items-center gap-2">
    <Text kind="body/regular/sm" color="subtle">
      {label}
    </Text>
    <SelectRoot value={value} onValueChange={onChange} size="small">
      <SelectTrigger
        className={triggerClassName}
        size="small"
        aria-label={label}
        // The trigger shows the raw value by default; map it back to the metric's label. Resolved
        // from the list rather than from the id so each chart keeps its own naming.
        renderValue={(v) =>
          typeof v === 'string' ? metrics.find((metric) => metric.id === v)?.label : undefined
        }
      />
      {/* Keep the dropdown readable even when the trigger is compact/narrow. */}
      <SelectContent className="min-w-48">
        <SelectListbox>
          {metrics.map((metric) => (
            <SelectItem key={metric.id} value={metric.id}>
              {metric.label}
            </SelectItem>
          ))}
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  </label>
);
