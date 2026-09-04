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

const optimizerInsightsPath = (workspace: string, path = '') =>
  `/apis/insights/v2/workspaces/${encodeURIComponent(String(workspace))}/insights${path}`;

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

/**
 * Insights analysis configs and analysis jobs.
 *
 * A run is triggered by creating an `analyze-job`, whose spec requires the
 * default/fast Model Entity pair. That pair is only resolvable from the
 * operator's CLI config, so it is captured on the agent's AnalysisConfig by
 * `nemo insights analysis enable --agent <name>`. Studio therefore reads the
 * stored config rather than trying to resolve models itself, and an agent with
 * no config cannot be analyzed from the UI.
 */

export interface AnalysisConfig {
  id?: string;
  name: string;
  agent: string;
  enabled: boolean;
  default_model: string;
  fast_model: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface AnalyzeJobSpec {
  agent: string;
  default_model: string;
  fast_model: string;
  ethos?: string;
  base_url?: string;
  since?: string;
  update_analysis_config?: boolean;
}

export interface CreateAnalysisJobRequest {
  name?: string;
  description?: string;
  spec: AnalyzeJobSpec;
}

export interface AnalysisJob {
  id?: string;
  name: string;
  workspace?: string;
  spec: AnalyzeJobSpec;
  status?: string;
  created_at?: string;
  [key: string]: unknown;
}

const insightsPath = (workspace: string, path: string) =>
  `/apis/insights/v2/workspaces/${encodeURIComponent(String(workspace))}${path}`;

export const insightsGetAnalysisConfig = (workspace: string, agent: string, signal?: AbortSignal) =>
  customFetch<AnalysisConfig>({
    url: insightsPath(workspace, `/analysis-configs/${encodeURIComponent(agent)}`),
    method: 'GET',
    signal,
  });

export const getInsightsGetAnalysisConfigQueryKey = (workspace: string, agent: string) =>
  [insightsPath(workspace, `/analysis-configs/${encodeURIComponent(agent)}`)] as const;

export const useInsightsGetAnalysisConfig = <TError = ErrorType<HTTPValidationError>>(
  workspace: string,
  agent: string,
  options?: QueryOptions<Awaited<ReturnType<typeof insightsGetAnalysisConfig>>, TError>,
  queryClient?: QueryClient
): UseQueryResult<Awaited<ReturnType<typeof insightsGetAnalysisConfig>>, TError> =>
  useQuery(
    {
      queryKey: getInsightsGetAnalysisConfigQueryKey(workspace, agent),
      queryFn: ({ signal }) => insightsGetAnalysisConfig(workspace, agent, signal),
      enabled: !!workspace && !!agent,
      ...options?.query,
    },
    queryClient
  );

/**
 * Enable periodic analysis and stamp the model pair onto the config, creating it if absent.
 *
 * This is the only write that can set the models — `PATCH` carries `enabled` alone — and it
 * always forces `enabled: true`, so a save that leaves an agent disabled must follow it with
 * {@link insightsDisableAnalysisConfig}.
 */
export const insightsEnableAnalysisConfig = (
  workspace: string,
  agent: string,
  data: { default_model: string; fast_model: string }
) =>
  customFetch<AnalysisConfig>({
    url: insightsPath(workspace, `/analysis-configs/${encodeURIComponent(agent)}/enable`),
    method: 'POST',
    data,
  });

export const insightsDisableAnalysisConfig = (workspace: string, agent: string) =>
  customFetch<AnalysisConfig>({
    url: insightsPath(workspace, `/analysis-configs/${encodeURIComponent(agent)}/disable`),
    method: 'POST',
  });

export const insightsCreateAnalysisJob = (workspace: string, data: CreateAnalysisJobRequest) =>
  customFetch<AnalysisJob>({
    url: insightsPath(workspace, '/jobs/analyze-job'),
    method: 'POST',
    data,
  });

export const useInsightsCreateAnalysisJob = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(
  options?: MutationOptions<
    Awaited<ReturnType<typeof insightsCreateAnalysisJob>>,
    { workspace: string; data: CreateAnalysisJobRequest },
    TError,
    TContext
  >,
  queryClient?: QueryClient
): UseMutationResult<
  Awaited<ReturnType<typeof insightsCreateAnalysisJob>>,
  TError,
  { workspace: string; data: CreateAnalysisJobRequest },
  TContext
> =>
  useMutation(
    {
      mutationKey: ['insightsCreateAnalysisJob'],
      mutationFn: ({ workspace, data }) => insightsCreateAnalysisJob(workspace, data),
      ...options?.mutation,
    },
    queryClient
  );
