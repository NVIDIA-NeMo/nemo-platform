// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import { useCopyToClipboard } from '@nemo/common/src/hooks/useCopyToClipboard';
import { useListSpans } from '@nemo/sdk/generated/platform/api';
import { Flex, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { SpanKindBadge } from '@studio/components/SpanKindBadge';
import { TraceSpanAccordionContent } from '@nemo/studio-plugins-example/intake-trace-detail/TraceSpanAccordionContent';
import {
  buildSpanHierarchyRows,
  formatCost,
  formatDurationMs,
  formatInteger,
  getSpanDisplayName,
  getSpanDurationMs,
  getSpanSubject,
  type SpanTableRow,
} from '@studio/util/intakeTelemetry';
import { Copy, ListTree } from 'lucide-react';
import { type FC, type MouseEvent, useMemo, useState } from 'react';

const TRACE_SPANS_PAGE_SIZE = 1000;
const HIERARCHY_SPACER_LIMIT = 12;

interface TraceSpanAccordionsProps {
  workspace: string;
  traceId: string;
  spanCount?: number;
}

interface CopyButtonProps {
  value: string;
  label: string;
}

/** Small copy action; stops propagation so it doesn't toggle the accordion row. */
const CopyButton: FC<CopyButtonProps> = ({ value, label }) => {
  const { copyToClipboard } = useCopyToClipboard();

  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    void copyToClipboard(value);
  };

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={handleClick}
      className="flex size-4 shrink-0 items-center justify-center text-secondary transition-colors hover:text-primary"
    >
      <Copy className="size-4" aria-hidden />
    </button>
  );
};

interface SpanTriggerLabelProps {
  span: SpanTableRow;
}

const SpanTriggerLabel: FC<SpanTriggerLabelProps> = ({ span }) => {
  const depth = span.hierarchyDepth;
  const hierarchyLabel =
    span.hierarchyStatus === 'parent_outside_page'
      ? 'Parent outside page'
      : span.hierarchyStatus === 'cycle_or_unreachable'
        ? 'Unresolved hierarchy'
        : undefined;

  return (
    <>
      {Array.from({ length: Math.min(depth, HIERARCHY_SPACER_LIMIT) }).map((_, index) => (
        <span
          key={`${span.span_id}-hierarchy-spacer-${index}`}
          aria-hidden
          className="w-[18px] shrink-0"
        />
      ))}
      {depth > 0 && (
        <span aria-hidden className="relative h-5 w-5 shrink-0">
          <span className="absolute left-0 top-1/2 w-full border-t border-base" />
          <span className="absolute left-0 top-0 h-1/2 border-l border-base" />
        </span>
      )}
      <Text kind="body/semibold/sm" className="shrink-0 truncate font-mono">
        {getSpanDisplayName(span)}
      </Text>
      <SpanKindBadge kind={span.kind} />
      <Text kind="body/regular/sm" className="min-w-0 flex-1 truncate text-secondary">
        {getSpanSubject(span)}
      </Text>
      {hierarchyLabel && (
        <Text kind="body/regular/xs" className="shrink-0 text-secondary">
          {hierarchyLabel}
        </Text>
      )}
    </>
  );
};

interface SpanTriggerMetaProps {
  span: SpanTableRow;
}

/** Right-aligned monospace token/cost/duration metrics + copy action. */
const SpanTriggerMeta: FC<SpanTriggerMetaProps> = ({ span }) => (
  <>
    {span.status && span.status !== 'success' && (
      <IntakeTelemetryStatusBadge status={span.status} />
    )}
    <Flex align="center" gap="density-xl" className="font-mono text-xs tabular-nums">
      {span.total_tokens !== null && span.total_tokens !== undefined && (
        <Text kind="body/regular/xs" className="font-mono text-primary">
          Tk <span className="text-secondary">{formatInteger(span.total_tokens)}</span>
        </Text>
      )}
      {span.cost_total_usd !== null && span.cost_total_usd !== undefined && (
        <Text kind="body/regular/xs" className="font-mono text-secondary">
          {formatCost(span.cost_total_usd)}
        </Text>
      )}
      <Text kind="body/regular/xs" className="font-mono text-secondary">
        {formatDurationMs(getSpanDurationMs(span))}
      </Text>
    </Flex>
    <CopyButton value={span.span_id} label="Copy span ID" />
  </>
);

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
    mode: 'summary',
    page: 1,
    page_size: TRACE_SPANS_PAGE_SIZE,
    sort: 'started_at',
  });

  const spanRows = useMemo(
    () => buildSpanHierarchyRows(spansResponse?.data ?? []),
    [spansResponse?.data]
  );

  const showSpanLimitMessage = spanCount !== undefined && spanCount > TRACE_SPANS_PAGE_SIZE;

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  return (
    <Stack gap="density-lg" className="min-w-0">
      <Flex align="center" gap="density-sm" className="min-w-0">
        <ListTree className="shrink-0" aria-hidden />
        <Text kind="body/semibold/md">Spans</Text>
      </Flex>
      {showSpanLimitMessage && (
        <Text kind="body/regular/sm" className="text-secondary">
          Showing first {TRACE_SPANS_PAGE_SIZE.toLocaleString()} of {spanCount.toLocaleString()}{' '}
          spans. Parent spans outside this page are marked in the hierarchy.
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
        <div className="overflow-hidden rounded-lg bg-surface-raised">
          <IntakeAccordion
            variant="row"
            value={openSpanIds}
            onValueChange={setOpenSpanIds}
            items={spanRows.map((span) => ({
              value: span.span_id,
              slotLabel: <SpanTriggerLabel span={span} />,
              slotEnd: <SpanTriggerMeta span={span} />,
              slotContent: openSpanIds.includes(span.span_id) ? (
                <TraceSpanAccordionContent
                  workspace={workspace}
                  spanId={span.span_id}
                  summarySpan={span}
                />
              ) : null,
            }))}
          />
        </div>
      )}
    </Stack>
  );
};
