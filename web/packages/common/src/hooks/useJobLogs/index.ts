// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getJobsPageJobLogsQueryKey, jobsPageJobLogs } from '@nemo/sdk/generated/platform/api';
import type {
  PlatformJobLog,
  PlatformJobLogPage,
  PlatformJobStatus,
} from '@nemo/sdk/generated/platform/schema';
import {
  useQuery,
  useQueryClient,
  type QueryObserverResult,
  type RefetchOptions,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { LOGS_MAX_FETCH_ITERATIONS, LOGS_MAX_PAGES, LOGS_PAGE_SIZE } from '../../constants';
import { CJobTerminalStatuses } from '../../constants/query';
import { getJobRefetchInterval } from '../../utils/query';

// After a job goes terminal, refetchInterval stops polling — but OTLP log
// shipping can still be in flight, so the final lines would be lost. Refetch a
// few times post-terminal to capture the tail. Bounded and self-clearing.
const LOG_SETTLE_DELAYS_MS = [2_000, 6_000, 12_000];

export interface UseJobLogsOptions {
  workspace: string;
  name: string;
  enabled?: boolean;
  jobStatus?: PlatformJobStatus;
  pageSize?: number;
  /** Max pages of logs to retain in memory. Defaults to LOGS_MAX_PAGES.
   *  Set to Infinity for download scenarios where all logs are needed. */
  maxPages?: number;
}

interface JobLogsQueryData {
  logs: PlatformJobLog[];
  total: number;
}

export interface UseJobLogsResult {
  data: PlatformJobLog[];
  isLoading: boolean;
  error: Error | null;
  total: number;
  refetch: (options?: RefetchOptions) => Promise<QueryObserverResult<JobLogsQueryData>>;
}

export function getJobLogsQueryKey(
  workspace: string,
  name: string
): [...ReturnType<typeof getJobsPageJobLogsQueryKey>, 'all'] {
  return [...getJobsPageJobLogsQueryKey(workspace, name), 'all'];
}

function getPageQueryKey(workspace: string, name: string, cursor: string | undefined) {
  return [...getJobsPageJobLogsQueryKey(workspace, name), 'page', cursor ?? 'initial'];
}

export const useJobLogs = ({
  workspace,
  name,
  enabled,
  jobStatus,
  pageSize = LOGS_PAGE_SIZE,
  maxPages = LOGS_MAX_PAGES,
}: UseJobLogsOptions): UseJobLogsResult => {
  const queryClient = useQueryClient();
  const queryKey = getJobLogsQueryKey(workspace, name);
  const maxRetainedLogs = maxPages * pageSize;

  const query = useQuery<JobLogsQueryData>({
    queryKey,
    queryFn: async ({ signal }) => {
      let allLogs: PlatformJobLog[] = [];
      let cursor: string | undefined;
      let total = 0;

      for (let i = 0; i < LOGS_MAX_FETCH_ITERATIONS; i++) {
        if (signal.aborted) break;

        const pageCursor = cursor;
        const pageKey = getPageQueryKey(workspace, name, pageCursor);
        const cached = queryClient.getQueryData<PlatformJobLogPage>(pageKey);
        const isCachedFullPage = cached !== undefined && cached.data.length >= pageSize;

        const page = await queryClient.fetchQuery({
          queryKey: pageKey,
          queryFn: ({ signal }) =>
            jobsPageJobLogs(workspace, name, { limit: pageSize, page_cursor: pageCursor }, signal),
          staleTime: isCachedFullPage ? Infinity : 0,
        });

        allLogs.push(...page.data);
        total = page.total;

        if (maxRetainedLogs !== Infinity && allLogs.length > maxRetainedLogs) {
          allLogs = allLogs.slice(-maxRetainedLogs);
        }

        if (!page.next_page || page.data.length === 0) break;
        cursor = page.next_page;
      }

      return { logs: allLogs, total };
    },
    enabled: enabled ?? !!(workspace && name),
    refetchInterval: () => getJobRefetchInterval(jobStatus),
  });

  const isTerminal = !!jobStatus && CJobTerminalStatuses.includes(jobStatus);
  const { refetch } = query;
  // Only settle-burst when the job COMPLETES while mounted (a non-terminal ->
  // terminal transition we actually observed) — not when mounting into an
  // already-terminal job, whose initial fetch already has the full log. This
  // also stops the burst re-firing on remount, e.g. re-expanding a collapsed
  // log panel on a finished job.
  const sawActiveRef = useRef(false);
  useEffect(() => {
    if (jobStatus && !isTerminal) sawActiveRef.current = true;
    if (!isTerminal || !sawActiveRef.current) return;
    const timers = LOG_SETTLE_DELAYS_MS.map((ms) => setTimeout(() => void refetch(), ms));
    return () => timers.forEach(clearTimeout);
  }, [jobStatus, isTerminal, refetch]);

  return {
    data: query.data?.logs ?? [],
    isLoading: query.isLoading,
    error: query.error,
    total: query.data?.total ?? 0,
    refetch: query.refetch,
  };
};
