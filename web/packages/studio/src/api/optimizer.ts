// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch, type ErrorType } from '@nemo/sdk/generated/fetchers/platform';
import type { HTTPValidationError, PaginationData } from '@nemo/sdk/generated/platform/schema';
import {
  type QueryClient,
  type UseMutationOptions,
  type UseMutationResult,
  type UseQueryOptions,
  type UseQueryResult,
  useMutation,
  useQuery,
} from '@tanstack/react-query';

/**
 * The Insights plugin is a NeMo Platform backend plugin whose routes are NOT
 * part of the generated SDK. We hand-write typed hooks against its endpoints
 * using `customFetch`, which applies the same base URL + OIDC auth handling as
 * the generated clients.
 *
 * Routes mount at `/apis/insights/v2/workspaces/{workspace}/...`.
 */

export type InsightStatus = 'open' | 'resolved' | 'deleted';

export interface Insight {
  /** Store-assigned id — used to fetch a single insight (`GET /insights/{id}`). */
  id: string;
  /** Entity name (unique slug within the workspace). */
  name: string;
  /** Short, human-readable sentence naming the core issue. */
  title: string;
  /** The actionable problem statement. */
  description: string;
  /** Registered agent name or local path this insight is about. */
  agent: string;
  /** Lifecycle state. Defaults to `open`. */
  status: InsightStatus;
  /** Intake trace ids identified as evidence for this insight. */
  trace_refs: string[];
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface InsightListItem extends Insight {
  /** Number of experiment groups linked to this insight, or null when unknown. */
  experiment_group_count: number | null;
  /** Newest start timestamp among the insight's currently referenced traces. */
  last_seen_at?: string | null;
}

export type OptimizerListInsightsParams = Record<string, unknown> & {
  page?: number;
  page_size?: number;
  sort?: string;
  filter?: Record<string, unknown>;
};

export interface InsightPage {
  data?: InsightListItem[];
  pagination?: PaginationData;
  [key: string]: unknown;
}

export type EvalAuthorRunStatus = 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export type EvalAuthorRunStage =
  | 'initializing'
  | 'materializing_traces'
  | 'analyzing_traces'
  | 'discovering_runner'
  | 'authoring_verifier'
  | 'validating'
  | 'publishing'
  | 'completed';

export type EvalAuthorCaptureStatus = 'complete' | 'partial' | 'unavailable';

export interface EvalAuthorRun {
  id: string;
  name: string;
  workspace: string;
  insight_id: string;
  status: EvalAuthorRunStatus;
  stage: EvalAuthorRunStage;
  evaluator_type: string;
  config: {
    max_traces: number;
    max_summary_tokens: number;
    max_validation_repair_attempts: number;
  };
  inputs: {
    agent: string;
    task_template: string;
    train_dataset: string;
    validation_dataset: string;
    trace_refs: string[];
  };
  models: {
    smart: string;
    fast: string;
  };
  provenance: {
    optimizer_branch: string;
    optimizer_commit: string;
    runner: string;
  };
  outputs: {
    artifact_fileset?: string | null;
    insight_suite?: string | null;
    train_dataset?: string | null;
    validation_dataset?: string | null;
    metric_names: string[];
    train_task_count: number;
    validation_task_count: number;
  };
  capture: {
    prompt: EvalAuthorCaptureStatus;
    trajectory: EvalAuthorCaptureStatus;
    redactions: boolean;
    redacted_fields: string[];
  };
  validation: {
    status: string;
    attempt_count: number;
  };
  summary: string;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface EvalAuthorRunPage {
  data?: EvalAuthorRun[];
  pagination?: PaginationData;
}

export interface OptimizerListEvalAuthorRunsParams extends Record<string, unknown> {
  page?: number;
  page_size?: number;
  sort?: string;
  insight_id?: string;
  status?: EvalAuthorRunStatus;
  created_at?: string;
}

const optimizerInsightsPath = (workspace: string, path = '') =>
  `/apis/insights/v2/workspaces/${encodeURIComponent(String(workspace))}/insights${path}`;

const optimizerEvalAuthorRunsPath = (workspace: string, path = '') =>
  `/apis/insights/v2/workspaces/${encodeURIComponent(String(workspace))}/eval-author-runs${path}`;

type QueryOptions<TData, TError> = {
  query?: Partial<UseQueryOptions<TData, TError, TData>>;
};

type MutationOptions<TData, TVariables, TError, TContext> = {
  mutation?: UseMutationOptions<TData, TError, TVariables, TContext>;
};

export interface UpdateInsightRequest {
  title?: string;
  agent?: string;
  description?: string;
  status?: InsightStatus;
  trace_refs?: string[];
}

export const optimizerListInsights = (
  workspace: string,
  params?: OptimizerListInsightsParams,
  signal?: AbortSignal
) =>
  customFetch<InsightPage>({
    url: optimizerInsightsPath(workspace),
    method: 'GET',
    params,
    signal,
  });

export const getOptimizerListInsightsQueryKey = (
  workspace: string,
  params?: OptimizerListInsightsParams
) => [optimizerInsightsPath(workspace), ...(params ? [params] : [])] as const;

export const useOptimizerListInsights = <TError = ErrorType<HTTPValidationError>>(
  workspace: string,
  params?: OptimizerListInsightsParams,
  options?: QueryOptions<Awaited<ReturnType<typeof optimizerListInsights>>, TError>,
  queryClient?: QueryClient
): UseQueryResult<Awaited<ReturnType<typeof optimizerListInsights>>, TError> =>
  useQuery(
    {
      queryKey: getOptimizerListInsightsQueryKey(workspace, params),
      queryFn: ({ signal }) => optimizerListInsights(workspace, params, signal),
      ...options?.query,
    },
    queryClient
  );

export const optimizerGetInsight = (workspace: string, insightId: string, signal?: AbortSignal) =>
  customFetch<Insight>({
    url: optimizerInsightsPath(workspace, `/${encodeURIComponent(insightId)}`),
    method: 'GET',
    signal,
  });

export const getOptimizerGetInsightQueryKey = (workspace: string, insightId: string) =>
  [optimizerInsightsPath(workspace, `/${encodeURIComponent(insightId)}`)] as const;

export const useOptimizerGetInsight = <TError = ErrorType<HTTPValidationError>>(
  workspace: string,
  insightId: string,
  options?: QueryOptions<Awaited<ReturnType<typeof optimizerGetInsight>>, TError>,
  queryClient?: QueryClient
): UseQueryResult<Awaited<ReturnType<typeof optimizerGetInsight>>, TError> =>
  useQuery(
    {
      queryKey: getOptimizerGetInsightQueryKey(workspace, insightId),
      queryFn: ({ signal }) => optimizerGetInsight(workspace, insightId, signal),
      enabled: !!insightId,
      ...options?.query,
    },
    queryClient
  );

export const optimizerUpdateInsight = (
  workspace: string,
  insightId: string,
  data: UpdateInsightRequest
) =>
  customFetch<Insight>({
    url: optimizerInsightsPath(workspace, `/${encodeURIComponent(insightId)}`),
    method: 'PATCH',
    data,
  });

export const useOptimizerUpdateInsight = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(
  options?: MutationOptions<
    Awaited<ReturnType<typeof optimizerUpdateInsight>>,
    { workspace: string; insightId: string; data: UpdateInsightRequest },
    TError,
    TContext
  >,
  queryClient?: QueryClient
): UseMutationResult<
  Awaited<ReturnType<typeof optimizerUpdateInsight>>,
  TError,
  { workspace: string; insightId: string; data: UpdateInsightRequest },
  TContext
> =>
  useMutation(
    {
      mutationKey: ['optimizerUpdateInsight'],
      mutationFn: ({ workspace, insightId, data }) =>
        optimizerUpdateInsight(workspace, insightId, data),
      ...options?.mutation,
    },
    queryClient
  );

export const optimizerListEvalAuthorRuns = (
  workspace: string,
  params?: OptimizerListEvalAuthorRunsParams,
  signal?: AbortSignal
) =>
  customFetch<EvalAuthorRunPage>({
    url: optimizerEvalAuthorRunsPath(workspace),
    method: 'GET',
    params,
    signal,
  });

export const getOptimizerListEvalAuthorRunsQueryKey = (
  workspace: string,
  params?: OptimizerListEvalAuthorRunsParams
) => [optimizerEvalAuthorRunsPath(workspace), ...(params ? [params] : [])] as const;

export const useOptimizerListEvalAuthorRuns = <TError = ErrorType<HTTPValidationError>>(
  workspace: string,
  params?: OptimizerListEvalAuthorRunsParams,
  options?: QueryOptions<Awaited<ReturnType<typeof optimizerListEvalAuthorRuns>>, TError>,
  queryClient?: QueryClient
): UseQueryResult<Awaited<ReturnType<typeof optimizerListEvalAuthorRuns>>, TError> =>
  useQuery(
    {
      queryKey: getOptimizerListEvalAuthorRunsQueryKey(workspace, params),
      queryFn: ({ signal }) => optimizerListEvalAuthorRuns(workspace, params, signal),
      ...options?.query,
    },
    queryClient
  );

export const optimizerGetEvalAuthorRun = (workspace: string, runId: string, signal?: AbortSignal) =>
  customFetch<EvalAuthorRun>({
    url: optimizerEvalAuthorRunsPath(workspace, `/${encodeURIComponent(runId)}`),
    method: 'GET',
    signal,
  });

export const getOptimizerGetEvalAuthorRunQueryKey = (workspace: string, runId: string) =>
  [optimizerEvalAuthorRunsPath(workspace, `/${encodeURIComponent(runId)}`)] as const;

export const useOptimizerGetEvalAuthorRun = <TError = ErrorType<HTTPValidationError>>(
  workspace: string,
  runId: string,
  options?: QueryOptions<Awaited<ReturnType<typeof optimizerGetEvalAuthorRun>>, TError>,
  queryClient?: QueryClient
): UseQueryResult<Awaited<ReturnType<typeof optimizerGetEvalAuthorRun>>, TError> =>
  useQuery(
    {
      queryKey: getOptimizerGetEvalAuthorRunQueryKey(workspace, runId),
      queryFn: ({ signal }) => optimizerGetEvalAuthorRun(workspace, runId, signal),
      enabled: !!runId,
      ...options?.query,
    },
    queryClient
  );
