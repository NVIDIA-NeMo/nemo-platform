// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { useListSpans } from '@nemo/sdk/generated/platform/api';
import { Accordion, Flex, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { getAgent00SpanSubject, getCollapsedInputPreview } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/agent00Subject';
import { TraceSpanAccordionContent } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/TraceSpanAccordionContent';
import { buildSpanHierarchyRows, formatDurationMs, getSpanDurationMs, type SpanTableRow } from '@studio/util/intakeTelemetry';
import { type FC, useMemo, useState } from 'react';

const TRACE_SPANS_PAGE_SIZE = 1000;

interface TraceSpanAccordionsProps {
  workspace: string;
  traceId: string;
  spanCount?: number;
}

interface SpanAccordionTriggerProps {
  span: SpanTableRow;
  isExpanded: boolean;
}

const SpanAccordionTrigger: FC<SpanAccordionTriggerProps> = ({ span, isExpanded }) => {
  const inputPreview = isExpanded ? undefined : getCollapsedInputPreview(span.input);

  return (
    <Flex align="center" gap="density-md" className="min-w-0 flex-1">
      <Text kind="body/semibold/sm" className="shrink-0 truncate font-mono">
        {getAgent00SpanSubject(span)}
      </Text>
      <Text kind="body/regular/sm" className="shrink-0 tabular-nums text-secondary">
        {formatDurationMs(getSpanDurationMs(span))}
      </Text>
      {inputPreview && (
        <Text kind="body/regular/sm" className="min-w-0 flex-1 truncate font-mono text-secondary">
          {inputPreview}
        </Text>
      )}
    </Flex>
  );
};

export const TraceSpanAccordions: FC<TraceSpanAccordionsProps> = ({
  workspace,
  traceId,
  spanCount,
}) => {
  const [openSpanIds, setOpenSpanIds] = useState<string[]>([]);

  const {
    data: spansResponse,
    isFetching,
    error,
  } = useListSpans(workspace, {
    filter: { trace_id: traceId },
    mode: 'detailed',
    page: 1,
    page_size: TRACE_SPANS_PAGE_SIZE,
    sort: 'started_at',
  });

  const spanRows = useMemo(
    () => buildSpanHierarchyRows(spansResponse?.data ?? []),
    [spansResponse?.data]
  );

  const showSpanLimitMessage =
    spanCount !== undefined && spanCount > TRACE_SPANS_PAGE_SIZE;

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  return (
    <Stack gap="density-lg" className="min-w-0">
      {showSpanLimitMessage && (
        <Text kind="body/regular/sm" className="text-secondary">
          Showing first {TRACE_SPANS_PAGE_SIZE.toLocaleString()} of{' '}
          {spanCount.toLocaleString()} spans.
        </Text>
      )}
      {isFetching && spanRows.length === 0 ? (
        <Flex align="center" justify="center" className="min-h-[200px]">
          <Spinner size="medium" />
        </Flex>
      ) : spanRows.length === 0 ? (
        <Text kind="body/regular/sm" className="text-secondary">
          No spans were found for this trace.
        </Text>
      ) : (
        <Accordion
          multiple
          chevronPosition="start"
          value={openSpanIds}
          onValueChange={setOpenSpanIds}
          items={spanRows.map((span) => ({
            value: span.span_id,
            slotTrigger: (
              <SpanAccordionTrigger
                span={span}
                isExpanded={openSpanIds.includes(span.span_id)}
              />
            ),
            slotContent: openSpanIds.includes(span.span_id) ? (
              <TraceSpanAccordionContent
                workspace={workspace}
                spanId={span.span_id}
                summarySpan={span}
              />
            ) : null,
          }))}
        />
      )}
    </Stack>
  );
};
