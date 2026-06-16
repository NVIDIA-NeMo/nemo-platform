// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { useGetTrace } from '@nemo/sdk/generated/platform/api';
import { Grid, Panel, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { IntakeSpansTable } from '@studio/components/IntakeSpansTable';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeTelemetryStatusBadge';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getIntakeSpanRoute } from '@studio/routes/utils';
import {
  EMPTY_VALUE,
  formatCost,
  formatDurationMs,
  formatInteger,
  formatMaybe,
} from '@studio/util/intakeTelemetry';
import { Activity, CircleAlert, Hash } from 'lucide-react';
import { type FC } from 'react';
import { Link } from 'react-router-dom';

const TRACE_SPANS_PAGE_SIZE = 1000;

export interface IntakeTraceDetailBodyProps {
  traceId: string;
  filterTogglePortalTargetId?: string;
  showSpans?: boolean;
}

export const IntakeTraceDetailBody: FC<IntakeTraceDetailBodyProps> = ({
  traceId,
  filterTogglePortalTargetId,
  showSpans = true,
}) => {
  const workspace = useWorkspaceFromPath();

  const {
    data: trace,
    error,
    isLoading,
  } = useGetTrace(workspace, traceId, {
    mode: 'detailed',
  });

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

  const showExperimentContext = Boolean(
    trace.experiment_context?.experiment_id || trace.experiment_context?.test_case_id
  );
  const showSpanLimitMessage =
    trace.span_count !== undefined && trace.span_count > TRACE_SPANS_PAGE_SIZE;
  const wrappingValueAttributes = {
    value: {
      className: 'block min-w-0 max-w-full break-all',
    },
  };

  const summaryPanels = (
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
            <KVPair label="Spans" value={formatInteger(trace.span_count)} orientation="vertical" />
            <KVPair
              label="Errors"
              value={formatInteger(trace.error_count)}
              orientation="vertical"
            />
            <KVPair label="Total Cost" value={formatCost(trace.cost_usd)} orientation="vertical" />
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
      {showExperimentContext && (
        <Panel
          elevation="high"
          slotIcon={<Hash />}
          slotHeading="Experiment Context"
          className="min-w-0 overflow-hidden"
        >
          <Stack gap="density-lg" className="min-w-0">
            <KVPair
              label="Summary"
              value={formatMaybe(
                trace.experiment_context?.experiment_id || trace.experiment_context?.test_case_id
              )}
              orientation="vertical"
              attributes={wrappingValueAttributes}
            />
            <KVPair
              label="Experiment ID"
              value={formatMaybe(trace.experiment_context?.experiment_id)}
              orientation="vertical"
              attributes={wrappingValueAttributes}
            />
            <KVPair
              label="Test Case ID"
              value={formatMaybe(trace.experiment_context?.test_case_id)}
              orientation="vertical"
              attributes={wrappingValueAttributes}
            />
          </Stack>
        </Panel>
      )}
    </Stack>
  );

  if (!showSpans) {
    return summaryPanels;
  }

  return (
    <Grid className="grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-density-2xl items-start">
      <Stack gap="density-md" className="min-w-0 min-h-[420px]">
        {showSpanLimitMessage && (
          <Text kind="body/regular/sm" className="text-secondary">
            Showing first {TRACE_SPANS_PAGE_SIZE.toLocaleString()} of{' '}
            {trace.span_count?.toLocaleString()} spans. Parent spans outside this page are marked in
            the hierarchy.
          </Text>
        )}
        <IntakeSpansTable
          workspace={workspace}
          filterTogglePortalTargetId={filterTogglePortalTargetId}
          fixedFilter={{ trace_id: trace.id }}
          defaultPageSize={TRACE_SPANS_PAGE_SIZE}
          mode="summary"
          showTraceColumn={false}
          showHierarchy
          emptyHeader="No Spans"
          emptyMessage="No spans were found for this trace."
        />
      </Stack>
      {summaryPanels}
    </Grid>
  );
};
