// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetSession, useListSpans, useListTraces } from '@nemo/sdk/generated/platform/api';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { type SessionExplorerData } from '@studio/components/IntakeDetail/TraceSpanAccordions';
import { buildSpanTree, type SessionTrajectory } from '@studio/util/intakeTelemetry';
import { useMemo } from 'react';

const SESSION_TRACES_PAGE_SIZE = 1000;

/**
 * Loads a session's summary, its traces, and their span trajectories — plus the
 * explorer bundle the span views need and the session's producer test_case_id.
 *
 * Shared by the single session detail view and the test-case comparison columns;
 * React Query dedupes the fetches when the same session renders in more than one
 * place (e.g. the primary column and the surrounding route both read it).
 */
export function useSessionTrajectories(workspace: string, sessionId: string) {
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
    [isSessionSpansFetching, sessionSpansError, sessionSpansResponse, trajectories]
  );

  const testCaseId = traces.find((trace) => trace.evaluation_context?.test_case_id)
    ?.evaluation_context?.test_case_id;

  return {
    session,
    sessionError,
    isSessionLoading,
    traces,
    tracesError,
    isTracesLoading,
    trajectories,
    explorer,
    testCaseId,
  };
}
