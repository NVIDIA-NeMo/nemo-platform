// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Flex, Text, Tooltip } from '@nvidia/foundations-react-core';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import { getSpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/registry';
import {
  formatCost,
  formatDurationMs,
  formatInteger,
  getSpanDurationMs,
  type SpanTableRow,
} from '@studio/util/intakeTelemetry';
import type { FC } from 'react';

// Compact unit-suffixed metric (e.g. "9tk", "3.50s"); the key name is the tooltip.
const SpanTriggerMetaValue: FC<{ label: string; value: string }> = ({ label, value }) => (
  <Tooltip slotContent={label} side="top">
    <Text
      kind="body/regular/xs"
      className="font-mono tabular-nums text-secondary whitespace-nowrap"
    >
      {value}
    </Text>
  </Tooltip>
);

/** Right-aligned token/cost/duration metrics; key names surface as tooltips. */
export const SpanTriggerMeta: FC<{ span: SpanTableRow }> = ({ span }) => {
  // A template may surface a kind-specific metric (e.g. an evaluator score or
  // guardrail decision) alongside the latency.
  const headerBadge = getSpanTemplate(span.kind).headerBadge?.(span);

  return (
    <>
      {span.status && span.status !== 'success' && (
        <IntakeTelemetryStatusBadge status={span.status} />
      )}
      <Flex align="center" gap="density-xl">
        {span.total_tokens !== null && span.total_tokens !== undefined && (
          <SpanTriggerMetaValue
            label="Total Tokens"
            value={`${formatInteger(span.total_tokens)}tk`}
          />
        )}
        {span.cost_total_usd !== null && span.cost_total_usd !== undefined && (
          <SpanTriggerMetaValue label="Total Cost" value={formatCost(span.cost_total_usd)} />
        )}
        {headerBadge !== undefined && (
          <Badge color={headerBadge.color ?? 'gray'} kind="solid">
            {headerBadge.text}
          </Badge>
        )}
        <SpanTriggerMetaValue
          label="Duration"
          value={formatDurationMs(getSpanDurationMs(span)).replace(/\s+/g, '')}
        />
      </Flex>
    </>
  );
};
