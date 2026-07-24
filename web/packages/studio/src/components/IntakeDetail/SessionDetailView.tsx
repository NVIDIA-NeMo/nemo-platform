// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack, StatusMessage } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { TraceDetailLayout } from '@studio/components/IntakeDetail/TraceDetailLayout';
import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { SessionSummaryHeader } from '@studio/components/IntakeDetail/TraceDetailSummaryHeader';
import { TraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import { TraceSpanAccordions } from '@studio/components/IntakeDetail/TraceSpanAccordions';
import {
  type TraceViewMode,
  TraceViewToolbar,
} from '@studio/components/IntakeDetail/TraceViewToolbar';
import { useSessionTrajectories } from '@studio/components/IntakeDetail/useSessionTrajectories';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import {
  type BreadcrumbsItemProps,
  useBreadcrumbs,
} from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { getIntakeSessionRoute, getIntakeTracesRoute } from '@studio/routes/utils';
import { CircleAlert } from 'lucide-react';
import { type FC, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

export type SessionDetailRouteContext =
  | { readonly kind: 'intake' }
  | {
      readonly kind: 'evaluation';
      readonly parentBreadcrumbs: BreadcrumbsItemProps[];
      readonly getSessionHref: (sessionId: string) => string;
      readonly headerActions?: ReactNode;
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
    session,
    sessionError,
    isSessionLoading,
    tracesError,
    isTracesLoading,
    trajectories,
    explorer,
    testCaseId,
  } = useSessionTrajectories(workspace, sessionId);
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
        <PageHeader
          className="p-0"
          slotHeading={title}
          slotActions={routeContext?.kind === 'evaluation' ? routeContext.headerActions : undefined}
        />
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
