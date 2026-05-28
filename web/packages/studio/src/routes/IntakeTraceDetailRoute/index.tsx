// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { useGetTrace } from '@nemo/sdk/generated/platform/api';
import {
  Grid,
  PageHeader,
  Panel,
  Stack,
  StatusMessage,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IntakeSpansTable } from '@studio/components/IntakeSpansTable';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIntakeSpanRoute, getIntakeTracesRoute } from '@studio/routes/utils';
import {
  EMPTY_VALUE,
  formatCost,
  formatDurationMs,
  formatInteger,
  formatMaybe,
  getEvaluationContextSummary,
  getTraceDisplayName,
  hasEvaluationContext,
} from '@studio/util/intakeTelemetry';
import { Activity, CircleAlert, Hash } from 'lucide-react';
import { type FC, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

const TRACE_SPANS_PAGE_SIZE = 1000;
const TRACE_DETAIL_SPANS_FILTER_TARGET_ID = 'trace-detail-spans-filter-action-target';

type TraceRouteParams = Record<typeof ROUTE_PARAMS.traceId, string | undefined>;

export const IntakeTraceDetailRoute: FC = () => {
  const { [ROUTE_PARAMS.traceId]: traceId } = useParams<TraceRouteParams>();

  if (!traceId) {
    return (
      <NotFound subheader="Trace Not Found" message="The trace route is missing a trace ID." />
    );
  }

  return <IntakeTraceDetailContent traceId={traceId} />;
};

interface IntakeTraceDetailContentProps {
  traceId: string;
}

const IntakeTraceDetailContent: FC<IntakeTraceDetailContentProps> = ({ traceId }) => {
  const workspace = useWorkspaceFromPath();

  const {
    data: trace,
    error,
    isLoading,
  } = useGetTrace(workspace, traceId, {
    mode: 'detailed',
  });

  const { setBreadcrumbs } = useBreadcrumbs();
  const traceBreadcrumbLabel = trace ? getTraceDisplayName(trace) : traceId;

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Intake',
        href: getIntakeTracesRoute(workspace),
      },
      {
        slotLabel: `Trace ${traceBreadcrumbLabel}`,
      },
    ]);
  }, [setBreadcrumbs, traceBreadcrumbLabel, workspace]);

  if (error?.response?.status === 404) {
    return (
      <NotFound
        subheader="Trace Not Found"
        message="The trace does not exist or you do not have permission to view it."
      />
    );
  }

  if (isLoading) {
    return <Loading description="Loading trace..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading trace"
        slotSubheading={error.message}
      />
    );
  }

  if (!trace) {
    return null;
  }

  const title = getTraceDisplayName(trace);
  const showEvaluationContext = hasEvaluationContext(trace.evaluation_context);
  const showSpanLimitMessage =
    trace.span_count !== undefined && trace.span_count > TRACE_SPANS_PAGE_SIZE;
  const wrappingValueAttributes = {
    value: {
      className: 'block min-w-0 max-w-full break-all',
    },
  };

  return (
    <AccessibleTitle title={`Trace ${title}`}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader
          className="p-0"
          slotHeading={`Trace ${title}`}
          slotActions={
            <div
              id={TRACE_DETAIL_SPANS_FILTER_TARGET_ID}
              className="flex shrink-0 items-center justify-end"
            />
          }
        />
        <Grid className="grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-density-2xl items-start">
          <Stack gap="density-md" className="min-w-0 min-h-[420px]">
            {showSpanLimitMessage && (
              <Text kind="body/regular/sm" className="text-secondary">
                Showing first {TRACE_SPANS_PAGE_SIZE.toLocaleString()} of{' '}
                {trace.span_count?.toLocaleString()} spans. Parent spans outside this page are
                marked in the hierarchy.
              </Text>
            )}
            <IntakeSpansTable
              workspace={workspace}
              filterTogglePortalTargetId={TRACE_DETAIL_SPANS_FILTER_TARGET_ID}
              fixedFilter={{ trace_id: trace.id }}
              defaultPageSize={TRACE_SPANS_PAGE_SIZE}
              mode="summary"
              showTraceColumn={false}
              showHierarchy
              emptyHeader="No Spans"
              emptyMessage="No spans were found for this trace."
            />
          </Stack>
          <Stack gap="density-2xl" className="min-w-0">
            <Panel
              elevation="high"
              slotIcon={<Activity />}
              slotHeading="Trace Summary"
              className="min-w-0 overflow-hidden"
            >
              <Stack gap="density-xl">
                <Grid className="grid-cols-2 gap-density-lg">
                  <KVPair
                    label="Started"
                    value={formatAbsoluteTimestamp(trace.started_at)}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Ended"
                    value={trace.ended_at ? formatAbsoluteTimestamp(trace.ended_at) : EMPTY_VALUE}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Duration"
                    value={formatDurationMs(trace.duration_ms)}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Spans"
                    value={formatInteger(trace.span_count)}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Errors"
                    value={formatInteger(trace.error_count)}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Total Cost"
                    value={formatCost(trace.cost_usd)}
                    orientation="vertical"
                  />
                </Grid>
                <Grid className="grid-cols-1 gap-density-lg min-w-0">
                  <KVPair
                    label="Trace ID"
                    value={trace.id}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Root Span"
                    value={
                      trace.root_span_id ? (
                        <Link
                          to={getIntakeSpanRoute(workspace, trace.root_span_id)}
                          className="break-all"
                        >
                          {trace.root_span_id}
                        </Link>
                      ) : (
                        EMPTY_VALUE
                      )
                    }
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Status"
                    value={<IntakeTelemetryStatusBadge status={trace.status} />}
                    orientation="vertical"
                  />
                  <KVPair
                    label="Session ID"
                    value={trace.session_id}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                </Grid>
              </Stack>
            </Panel>
            {showEvaluationContext && (
              <Panel
                elevation="high"
                slotIcon={<Hash />}
                slotHeading="Evaluation Context"
                className="min-w-0 overflow-hidden"
              >
                <Stack gap="density-lg" className="min-w-0">
                  <KVPair
                    label="Summary"
                    value={getEvaluationContextSummary(trace.evaluation_context)}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Evaluation ID"
                    value={formatMaybe(trace.evaluation_context?.evaluation_id)}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Run ID"
                    value={formatMaybe(trace.evaluation_context?.evaluation_run_id)}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Dataset"
                    value={formatMaybe(trace.evaluation_context?.dataset_name)}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                  <KVPair
                    label="Test Case"
                    value={formatMaybe(trace.evaluation_context?.test_case_id)}
                    orientation="vertical"
                    attributes={wrappingValueAttributes}
                  />
                </Stack>
              </Panel>
            )}
          </Stack>
        </Grid>
      </Stack>
    </AccessibleTitle>
  );
};
