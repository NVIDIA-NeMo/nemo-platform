// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetSession, useListSpans, useListTraces } from '@nemo/sdk/generated/platform/api';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { PageHeader, Stack, StatusMessage } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { TraceDetailLayout } from '@studio/components/IntakeDetail/TraceDetailLayout';
import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { SessionSummaryHeader } from '@studio/components/IntakeDetail/TraceDetailSummaryHeader';
import { TraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import {
  type SessionExplorerData,
  TraceSpanAccordions,
} from '@studio/components/IntakeDetail/TraceSpanAccordions';
import {
  type TraceViewMode,
  TraceViewToolbar,
} from '@studio/components/IntakeDetail/TraceViewToolbar';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import {
  type BreadcrumbsItemProps,
  useBreadcrumbs,
} from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { getIntakeSessionRoute, getIntakeTracesRoute } from '@studio/routes/utils';
import { buildSpanTree, type SessionTrajectory } from '@studio/util/intakeTelemetry';
import { CircleAlert } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

const SESSION_TRACES_PAGE_SIZE = 1000;

export type SessionDetailRouteContext =
  | { readonly kind: 'intake' }
  | {
      readonly kind: 'evaluation';
      readonly parentBreadcrumbs: BreadcrumbsItemProps[];
      readonly getSessionHref: (sessionId: string) => string;
    };

interface SessionDetailViewProps {
  workspace: string;
  sessionId: string;
  routeContext?: SessionDetailRouteContext;
}

/** Session detail shell: session summary at the root, trace/span detail in URL-selected children. */
export const SessionDetailView: FC<SessionDetailViewProps> = ({
  workspace,
  sessionId,
  routeContext,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const traceId = searchParams.get(QUERY_PARAMETERS.traceId) || undefined;
  const linkedSpanId = searchParams.get(QUERY_PARAMETERS.spanId) || undefined;
  const [viewMode, setViewMode] = useState<TraceViewMode>('tree');
  const defaultGetSessionHref = useCallback(
    (targetSessionId: string) => getIntakeSessionRoute(workspace, targetSessionId),
    [workspace]
  );
  const getSessionHref =
    routeContext?.kind === 'evaluation' ? routeContext.getSessionHref : defaultGetSessionHref;

  const {
    data: session,
    error: sessionError,
    isLoading: isSessionLoading,
  } = useGetSession(workspace, sessionId);

  const {
    data: tracesResponse,
    error: tracesError,
    isLoading: isTracesLoading,
  } = useListTraces(workspace, {
    filter: { session_id: sessionId },
    mode: 'summary',
    page: 1,
    page_size: SESSION_TRACES_PAGE_SIZE,
    sort: 'started_at',
  });
  const traces = useMemo(() => tracesResponse?.data ?? [], [tracesResponse?.data]);
  const {
    data: sessionSpansResponse,
    error: sessionSpansError,
    isFetching: isSessionSpansFetching,
  } = useListSpans(workspace, {
    filter: { session_id: sessionId },
    mode: 'summary',
    page: 1,
    page_size: SESSION_TRACES_PAGE_SIZE,
    sort: 'started_at',
  });
  const trajectories = useMemo<SessionTrajectory[]>(() => {
    const groupedSpans = new Map<string, Span[]>();
    for (const span of sessionSpansResponse?.data ?? []) {
      if (!span.trace_id) continue;
      const traceSpans = groupedSpans.get(span.trace_id) ?? [];
      traceSpans.push(span);
      groupedSpans.set(span.trace_id, traceSpans);
    }
    return traces.map((trace) => {
      const spans = groupedSpans.get(trace.id) ?? [];
      return { trace, spans, spanTree: buildSpanTree(spans) };
    });
  }, [sessionSpansResponse?.data, traces]);
  const explorer = useMemo<SessionExplorerData>(
    () => ({
      trajectories,
      spansLoaded: sessionSpansResponse !== undefined,
      spansError: sessionSpansError,
      isSpansFetching: isSessionSpansFetching,
      spanPageSize: SESSION_TRACES_PAGE_SIZE,
      spanTotal: sessionSpansResponse?.pagination?.total_results ?? 0,
    }),
    [
      isSessionSpansFetching,
      sessionSpansError,
      sessionSpansResponse,
      trajectories,
    ]
  );
  const testCaseId = traces.find((trace) => trace.evaluation_context?.test_case_id)
    ?.evaluation_context?.test_case_id;
  const title =
    routeContext?.kind === 'evaluation' && testCaseId
      ? `Test case: ${testCaseId}`
      : `Session ${sessionId}`;
  const sessionHref = getSessionHref(sessionId);
  const baseBreadcrumbs = useMemo(
    () =>
      routeContext?.kind === 'evaluation'
        ? routeContext.parentBreadcrumbs
        : [{ slotLabel: 'Intake', href: getIntakeTracesRoute(workspace) }],
    [routeContext, workspace]
  );
  const traceParentBreadcrumbs = useMemo(
    () => [...baseBreadcrumbs, { slotLabel: title, href: sessionHref }],
    [baseBreadcrumbs, sessionHref, title]
  );
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    if (!traceId) setBreadcrumbs([...baseBreadcrumbs, { slotLabel: title }]);
  }, [baseBreadcrumbs, setBreadcrumbs, title, traceId]);

  useEffect(() => {
    if (traceId || !linkedSpanId) return;
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete(QUERY_PARAMETERS.spanId);
        return next;
      },
      { replace: true }
    );
  }, [linkedSpanId, setSearchParams, traceId]);

  const handleSelectSession = useCallback(() => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.delete(QUERY_PARAMETERS.traceId);
      next.delete(QUERY_PARAMETERS.spanId);
      return next;
    });
  }, [setSearchParams]);

  const handleSelectTrace = useCallback(
    (targetTraceId: string) => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set(QUERY_PARAMETERS.traceId, targetTraceId);
        next.delete(QUERY_PARAMETERS.spanId);
        return next;
      });
    },
    [setSearchParams]
  );

  const handleSelectSidebarSpan = useCallback(
    (spanId: string, targetTraceId: string) => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set(QUERY_PARAMETERS.traceId, targetTraceId);
        next.set(QUERY_PARAMETERS.spanId, spanId);
        return next;
      });
    },
    [setSearchParams]
  );

  if (sessionError?.response?.status === 404) {
    return (
      <NotFound
        subheader="Session Not Found"
        message="The session does not exist or you do not have permission to view it."
      />
    );
  }

  if (isSessionLoading || isTracesLoading) {
    return <Loading description="Loading session..." />;
  }

  const error = sessionError ?? tracesError;
  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading session"
        slotSubheading={error.message}
      />
    );
  }

  if (!session) return null;

  return (
    <AccessibleTitle title={title}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader className="p-0" slotHeading={title} />
        <div data-testid="session-summary-header" className="w-full min-w-0">
          <SessionSummaryHeader session={session} />
        </div>
        {traceId ? (
          <TraceDetailView
            workspace={workspace}
            traceId={traceId}
            sessionId={sessionId}
            parentBreadcrumbs={traceParentBreadcrumbs}
            traceSummary={trajectories.find(({ trace }) => trace.id === traceId)?.trace}
          >
            {(trace) => (
              <TraceSpanAccordions
                workspace={workspace}
                trace={trace}
                explorer={explorer}
                onSelectSession={handleSelectSession}
                onSelectTrace={handleSelectTrace}
                sessionDurationMs={session.duration_ms}
                sessionErrored={session.status === 'error'}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
              />
            )}
          </TraceDetailView>
        ) : (
          <Stack gap="density-lg" className="min-w-0">
            <TraceViewToolbar viewMode={viewMode} onViewModeChange={setViewMode} />
            <TraceDetailLayout
              navigation={
                <TraceSpanTree
                  trajectories={trajectories}
                  sessionDurationMs={session.duration_ms}
                  sessionErrored={session.status === 'error'}
                  sessionActive
                  activeSpanId={null}
                  onSelectSpan={handleSelectSidebarSpan}
                  onSelectTrace={handleSelectTrace}
                  onSelectSession={handleSelectSession}
                />
              }
            >
              {null}
            </TraceDetailLayout>
          </Stack>
        )}
      </Stack>
    </AccessibleTitle>
  );
};
