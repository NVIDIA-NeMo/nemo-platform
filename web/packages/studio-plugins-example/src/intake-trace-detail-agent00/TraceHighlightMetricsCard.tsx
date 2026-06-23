// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Flex } from '@nvidia/foundations-react-core';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { HighlightMetricsCardLayout } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/HighlightMetricsCardLayout';
import { HighlightMetricItem } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/keyValueTypes';
import { buildTraceHighlightMetrics } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/traceKeyValues';
import type { FC } from 'react';
import { useMemo } from 'react';

interface TraceHighlightMetricsCardProps {
  trace: Trace;
}

export const TraceHighlightMetricsCard: FC<TraceHighlightMetricsCardProps> = ({ trace }) => {
  const metrics = useMemo(() => buildTraceHighlightMetrics(trace), [trace]);

  return (
    <HighlightMetricsCardLayout
      leading={
        <HighlightMetricItem
          label="Status"
          value={<IntakeTelemetryStatusBadge status={trace.status} />}
        />
      }
      metrics={metrics}
    />
  );
};
