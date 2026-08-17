// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListTraces } from '@nemo/sdk/generated/platform/api';
import type { TraceFilter } from '@nemo/sdk/generated/platform/schema';
import type { TraceStatisticsRange } from '@studio/components/AgentTraceStatistics/types';
import { keepPreviousData } from '@tanstack/react-query';
import { useMemo } from 'react';

/** ClickHouse caps a page at 1000; one page is plenty to average a month of runs. */
const TRACE_PAGE_SIZE = 1000;

const RANGE_MS: Record<TraceStatisticsRange, number> = {
  day: 24 * 60 * 60 * 1000,
  week: 7 * 24 * 60 * 60 * 1000,
  month: 30 * 24 * 60 * 60 * 1000,
};

/**
 * Intake returns naive UTC timestamps (`2026-08-17T17:42:40.999490`). `new Date` reads a string
 * with no zone designator as *local* time, which slides every point by the browser's offset — so
 * pin it to UTC before bucketing.
 */
const parseUtcTimestamp = (value: string): Date =>
  new Date(value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);

interface UseOverviewTracesParams {
  workspace: string;
  range: TraceStatisticsRange;
  enabled: boolean;
}

/**
 * Traces backing the overview statistics.
 *
 * Scoped to the workspace, not the agent: Intake has no agent attribution on a trace
 * (`TraceFilter` exposes id/session/status/started_at/evaluation only), so there is nothing to
 * narrow on yet. Swap in an `agent` filter here once the ingest path records it.
 */
export const useOverviewTraces = ({ workspace, range, enabled }: UseOverviewTracesParams) => {
  const since = useMemo(() => {
    const now = Date.now();
    const minute = 60 * 1000;
    return new Date(Math.floor(now / minute) * minute - RANGE_MS[range]).toISOString();
  }, [range]);

  const filter: TraceFilter = { started_at: { $gte: since } };

  const { data, isPending } = useListTraces(
    workspace,
    {
      filter,
      mode: 'preview',
      page: 1,
      page_size: TRACE_PAGE_SIZE,
      sort: '-started_at',
    },
    { query: { enabled: enabled && !!workspace, placeholderData: keepPreviousData } }
  );

  const traces = useMemo(
    () =>
      (data?.data ?? []).map((trace) => ({
        startedAt: parseUtcTimestamp(trace.started_at),
        durationMs: trace.duration_ms,
        totalTokens: trace.total_tokens,
        costUsd: trace.cost_usd,
      })),
    [data]
  );

  return { traces, isPending: isPending && enabled };
};
