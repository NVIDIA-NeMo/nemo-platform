// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { useGetSpan } from '@nemo/sdk/generated/platform/api';
import {
  CodeSnippet,
  Grid,
  PageHeader,
  Panel,
  Stack,
  StatusMessage,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IntakeAnnotationsPanel } from '@studio/components/IntakeAnnotationsPanel';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  getIntakeSpanRoute,
  getIntakeTraceRoute,
  getIntakeTracesRoute,
} from '@studio/routes/utils';
import {
  EMPTY_VALUE,
  formatCost,
  formatDurationMs,
  formatInteger,
  formatMaybe,
  getEvaluationContextSummary,
  getSpanDisplayName,
  getSpanDurationMs,
  hasEvaluationContext,
} from '@studio/util/intakeTelemetry';
import { Activity, CircleAlert, Coins } from 'lucide-react';
import { type FC, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

const truncatedValueAttributes = {
  value: {
    className: 'block min-w-0 max-w-full truncate',
  },
};

interface SpanContentBlockProps {
  label: string;
  value: string | null | undefined;
  emptyMessage: string;
}

const SpanContentBlock: FC<SpanContentBlockProps> = ({ label, value, emptyMessage }) => {
  const content = value?.trim();

  return (
    <Stack gap="density-md" className="min-w-0">
      <Text kind="label/bold/sm" className="text-secondary">
        {label}
      </Text>
      {content ? (
        <CodeSnippet
          value={content}
          language="markdown"
          kind="block"
          collapsible
          defaultOpen
          attributes={{
            CodeSnippetCode: {
              className:
                'max-h-[420px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
            },
          }}
        />
      ) : (
        <div className="flex min-h-[120px] items-center rounded-md border border-dashed border-base bg-surface-raised p-density-xl">
          <Text kind="body/regular/sm" className="text-secondary">
            {emptyMessage}
          </Text>
        </div>
      )}
    </Stack>
  );
};

type SpanRouteParams = Record<typeof ROUTE_PARAMS.spanId, string | undefined>;

export const IntakeSpanDetailRoute: FC = () => {
  const { [ROUTE_PARAMS.spanId]: spanId } = useParams<SpanRouteParams>();

  if (!spanId) {
    return <NotFound subheader="Span Not Found" message="The span route is missing a span ID." />;
  }

  return <IntakeSpanDetailContent spanId={spanId} />;
};

interface IntakeSpanDetailContentProps {
  spanId: string;
}

const IntakeSpanDetailContent: FC<IntakeSpanDetailContentProps> = ({ spanId }) => {
  const workspace = useWorkspaceFromPath();

  const { data: span, error, isLoading } = useGetSpan(workspace, spanId);
  const { setBreadcrumbs } = useBreadcrumbs();
  const spanBreadcrumbLabel = span ? getSpanDisplayName(span) : spanId;

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Intake',
        href: getIntakeTracesRoute(workspace),
      },
      ...(span?.trace_id
        ? [
            {
              slotLabel: `Trace ${span.trace_id}`,
              href: getIntakeTraceRoute(workspace, span.trace_id),
            },
          ]
        : []),
      {
        slotLabel: `Span ${spanBreadcrumbLabel}`,
      },
    ]);
  }, [setBreadcrumbs, span?.trace_id, spanBreadcrumbLabel, workspace]);

  if (error?.response?.status === 404) {
    return (
      <NotFound
        subheader="Span Not Found"
        message="The span does not exist or you do not have permission to view it."
      />
    );
  }

  if (isLoading) {
    return <Loading description="Loading span..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading span"
        slotSubheading={error.message}
      />
    );
  }

  if (!span) {
    return null;
  }

  const title = getSpanDisplayName(span);
  const showEvaluationContext = hasEvaluationContext(span.evaluation_context);

  return (
    <AccessibleTitle title={`Span ${title}`}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader className="p-0" slotHeading={title} />
        <Grid className="grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)] gap-density-2xl">
          <Panel
            elevation="high"
            slotIcon={<Activity />}
            slotHeading="Span Summary"
            className="min-w-0 overflow-hidden"
          >
            <Stack gap="density-xl">
              <Grid className="grid-cols-1 md:grid-cols-2 gap-density-lg">
                <KVPair label="Span ID" value={span.span_id} orientation="vertical" truncate />
                <KVPair label="Kind" value={span.kind} orientation="vertical" />
                <KVPair
                  label="Status"
                  value={<IntakeTelemetryStatusBadge status={span.status} />}
                  orientation="vertical"
                />
                <KVPair label="Source" value={formatMaybe(span.source)} orientation="vertical" />
                <KVPair
                  label="Trace"
                  value={
                    span.trace_id ? (
                      <Link to={getIntakeTraceRoute(workspace, span.trace_id)}>
                        {span.trace_id}
                      </Link>
                    ) : (
                      EMPTY_VALUE
                    )
                  }
                  orientation="vertical"
                  truncate
                />
                <KVPair
                  label="Parent Span"
                  value={
                    span.parent_span_id ? (
                      <Link to={getIntakeSpanRoute(workspace, span.parent_span_id)}>
                        {span.parent_span_id}
                      </Link>
                    ) : (
                      EMPTY_VALUE
                    )
                  }
                  orientation="vertical"
                  truncate
                />
                <KVPair
                  label="Started"
                  value={formatAbsoluteTimestamp(span.started_at)}
                  orientation="vertical"
                />
                <KVPair
                  label="Ended"
                  value={span.ended_at ? formatAbsoluteTimestamp(span.ended_at) : EMPTY_VALUE}
                  orientation="vertical"
                />
                <KVPair
                  label="Duration"
                  value={formatDurationMs(getSpanDurationMs(span))}
                  orientation="vertical"
                />
                <KVPair
                  label="Session ID"
                  value={span.session_id}
                  orientation="vertical"
                  attributes={truncatedValueAttributes}
                />
                <KVPair
                  label="Project"
                  value={formatMaybe(span.project)}
                  orientation="vertical"
                  attributes={truncatedValueAttributes}
                />
                <KVPair
                  label="Model"
                  value={formatMaybe(span.model)}
                  orientation="vertical"
                  attributes={truncatedValueAttributes}
                />
                <KVPair
                  label="Provider"
                  value={formatMaybe(span.provider)}
                  orientation="vertical"
                  attributes={truncatedValueAttributes}
                />
                {showEvaluationContext && (
                  <KVPair
                    label="Evaluation"
                    value={getEvaluationContextSummary(span.evaluation_context)}
                    orientation="vertical"
                    attributes={truncatedValueAttributes}
                  />
                )}
              </Grid>
              {span.status === 'error' && (
                <Grid className="grid-cols-1 md:grid-cols-2 gap-density-lg">
                  <KVPair
                    label="Error Type"
                    value={formatMaybe(span.error_type)}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Error Message"
                    value={formatMaybe(span.error_message)}
                    orientation="vertical"
                  />
                </Grid>
              )}
              {(span.input?.trim() || span.output?.trim()) && (
                <Stack gap="density-2xl" className="min-w-0">
                  <SpanContentBlock
                    label="Input"
                    value={span.input}
                    emptyMessage="No input payload was captured for this span."
                  />
                  <SpanContentBlock
                    label="Output"
                    value={span.output}
                    emptyMessage="No output payload was captured for this span."
                  />
                </Stack>
              )}
            </Stack>
          </Panel>
          <Stack gap="density-2xl" className="min-w-0">
            <Panel
              elevation="high"
              slotIcon={<Coins />}
              slotHeading="Usage"
              className="min-w-0 overflow-hidden"
            >
              <Grid className="grid-cols-2 gap-density-lg">
                <KVPair
                  label="Input Tokens"
                  value={formatInteger(span.input_tokens)}
                  orientation="vertical"
                />
                <KVPair
                  label="Output Tokens"
                  value={formatInteger(span.output_tokens)}
                  orientation="vertical"
                />
                <KVPair
                  label="Cached Tokens"
                  value={formatInteger(span.cached_tokens)}
                  orientation="vertical"
                />
                <KVPair
                  label="Total Tokens"
                  value={formatInteger(span.total_tokens)}
                  orientation="vertical"
                />
                <KVPair
                  label="Input Cost"
                  value={formatCost(span.cost_input_usd)}
                  orientation="vertical"
                />
                <KVPair
                  label="Output Cost"
                  value={formatCost(span.cost_output_usd)}
                  orientation="vertical"
                />
                <KVPair
                  label="Total Cost"
                  value={formatCost(span.cost_total_usd)}
                  orientation="vertical"
                />
              </Grid>
            </Panel>
            <IntakeAnnotationsPanel
              workspace={workspace}
              spanId={span.span_id}
              sessionId={span.session_id}
            />
          </Stack>
        </Grid>
      </Stack>
    </AccessibleTitle>
  );
};
