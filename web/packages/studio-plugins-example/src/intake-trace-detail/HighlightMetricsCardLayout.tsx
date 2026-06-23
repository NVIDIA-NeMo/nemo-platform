// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Divider, Flex, Panel } from '@nvidia/foundations-react-core';
import {
  HighlightMetricItem,
  type HighlightMetric,
} from '@nemo/studio-plugins-example/intake-trace-detail/keyValueTypes';
import type { FC, ReactNode } from 'react';

interface HighlightMetricsCardLayoutProps {
  leading: ReactNode;
  metrics: readonly HighlightMetric[];
}

export const HighlightMetricsCardLayout: FC<HighlightMetricsCardLayoutProps> = ({
  leading,
  metrics,
}) => (
  <Panel elevation="high" className="min-w-0">
    <Flex align="stretch" gap="density-2xl" className="w-full">
      <div className="shrink-0">{leading}</div>
      <Divider orientation="vertical" className="shrink-0 self-stretch" />
      <div className="ml-auto flex max-w-full flex-nowrap items-start gap-4 overflow-x-auto">
        {metrics.map((metric) => (
          <HighlightMetricItem key={metric.id} label={metric.label} value={metric.value} />
        ))}
      </div>
    </Flex>
  </Panel>
);
