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
import {
  metricLabel,
  type ParetoMetric,
} from '@studio/components/charts/ExperimentGroupParetoChart/utils';
import type { FC } from 'react';

interface MetricSelectProps {
  label: string;
  value: string;
  metrics: readonly ParetoMetric[];
  onChange: (id: string) => void;
}

/** A labeled dropdown for choosing the metric on one Pareto axis. */
export const MetricSelect: FC<MetricSelectProps> = ({ label, value, metrics, onChange }) => (
  <label className="flex items-center gap-2">
    <Text kind="body/regular/sm" color="subtle">
      {label}
    </Text>
    <SelectRoot value={value} onValueChange={onChange} size="small">
      <SelectTrigger
        className="w-26"
        size="small"
        aria-label={label}
        // The trigger shows the raw value by default; map it back to the metric's label.
        renderValue={(v) => (typeof v === 'string' && v ? metricLabel(v) : undefined)}
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
