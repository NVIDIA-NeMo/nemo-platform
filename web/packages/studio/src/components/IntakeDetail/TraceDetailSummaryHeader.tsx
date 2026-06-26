// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Flex, Stack, Text, Tooltip } from '@nvidia/foundations-react-core';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import type { HighlightMetricDetail } from '@studio/components/IntakeDetail/IntakeComponents/keyValueTypes';
import { buildTraceHighlightMetrics } from '@studio/components/IntakeDetail/IntakeComponents/traceKeyValues';
import { type FC, type ReactNode, useMemo } from 'react';

const TraceSummaryMetricItem: FC<{
  label: string;
  value: ReactNode;
  details?: readonly HighlightMetricDetail[];
}> = ({ label, value, details }) => {
  const hasDetails = !!details && details.length > 0;
  const item = (
    <Stack gap="density-xs" className="w-max shrink-0">
      <Text kind="label/regular/md" className="whitespace-nowrap text-secondary">
        {label}
      </Text>
      {typeof value === 'string' ? (
        <Text
          kind="title/xs"
          className={`whitespace-nowrap text-primary${
            // Dotted underline signals an on-hover breakdown, matching the
            // click-to-expand timestamps in the span templates.
            hasDetails
              ? ' cursor-help underline decoration-dotted decoration-from-font underline-offset-2'
              : ''
          }`}
        >
          {value}
        </Text>
      ) : (
        value
      )}
    </Stack>
  );

  if (!hasDetails) {
    return item;
  }

  return (
    <Tooltip
      side="bottom"
      slotContent={
        <Stack gap="density-xs" className="min-w-[10rem]">
          {details.map((detail) => (
            <div key={detail.id} className="flex items-center justify-between gap-density-xl">
              <Text kind="label/regular/sm" className="whitespace-nowrap text-secondary">
                {detail.label}
              </Text>
              <Text kind="label/regular/sm" className="whitespace-nowrap font-mono">
                {detail.value}
              </Text>
            </div>
          ))}
        </Stack>
      }
    >
      {item}
    </Tooltip>
  );
};

// Timestamps read as data, not headline numbers — small mono, no title styling.
const dateValue = (value: string) => (
  <Text kind="body/regular/sm" className="whitespace-nowrap font-mono text-primary">
    {value}
  </Text>
);

interface TraceSummaryHeaderProps {
  trace: Trace;
}

/** Inline summary strip below the page title: status, timing, and headline metrics. */
export const TraceSummaryHeader: FC<TraceSummaryHeaderProps> = ({ trace }) => {
  const metrics = useMemo(() => buildTraceHighlightMetrics(trace), [trace]);
  const started = trace.started_at ? formatAbsoluteTimestamp(trace.started_at) : undefined;
  const ended = trace.ended_at ? formatAbsoluteTimestamp(trace.ended_at) : undefined;

  return (
    <Flex align="stretch" gap="density-2xl" className="w-full min-w-0">
      <Flex gap="density-2xl" align="start" className="shrink-0">
        <TraceSummaryMetricItem
          label="Status"
          value={<IntakeTelemetryStatusBadge status={trace.status} />}
        />
        {started ? <TraceSummaryMetricItem label="Started" value={dateValue(started)} /> : null}
        {ended ? <TraceSummaryMetricItem label="Ended" value={dateValue(ended)} /> : null}
      </Flex>
      <div className="ml-auto flex max-w-full flex-nowrap items-start gap-4 overflow-x-auto">
        {metrics.map((metric) => (
          <TraceSummaryMetricItem
            key={metric.id}
            label={metric.label}
            value={metric.value}
            details={metric.details}
          />
        ))}
      </div>
    </Flex>
  );
};
