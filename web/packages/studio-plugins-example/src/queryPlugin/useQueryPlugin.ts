// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import { useQuery, type UseQueryOptions } from '@tanstack/react-query';

export interface QueryPluginResult<TData = unknown> {
  query_plugin_id: string;
  data: TData;
}

export interface QueryPluginParams {
  experiment_id: string;
}

/** True when the backend uses the generic query-plugin wrapper (platform OpenAPI contract). */
export function isQueryPluginResult(value: unknown): value is QueryPluginResult {
  return (
    value !== null &&
    typeof value === 'object' &&
    'query_plugin_id' in value &&
    'data' in value &&
    typeof (value as QueryPluginResult).query_plugin_id === 'string'
  );
}

/**
 * Accept both response shapes:
 * - generic API: `{ query_plugin_id, data }`
 * - legacy per-plugin routes: plugin output JSON at the top level
 */
export function normalizeQueryPluginResult<TData>(
  queryPluginId: string,
  response: unknown,
): QueryPluginResult<TData> {
  if (isQueryPluginResult(response)) {
    return response as QueryPluginResult<TData>;
  }
  return { query_plugin_id: queryPluginId, data: response as TData };
}

export const getQueryPluginQueryKey = (
  workspace: string,
  queryPluginId: string,
  params: QueryPluginParams,
) => ['query-plugin', workspace, queryPluginId, params] as const;

export async function fetchQueryPlugin<TData>(
  workspace: string,
  queryPluginId: string,
  params: QueryPluginParams,
): Promise<QueryPluginResult<TData>> {
  const response = await customFetch<unknown>({
    url: `/apis/intake/v2/workspaces/${encodeURIComponent(workspace)}/query-plugins/${encodeURIComponent(queryPluginId)}`,
    method: 'GET',
    params,
  });
  return normalizeQueryPluginResult<TData>(queryPluginId, response);
}

export function useQueryPlugin<TData>(
  workspace: string,
  queryPluginId: string,
  params: QueryPluginParams,
  options?: Pick<UseQueryOptions<QueryPluginResult<TData>, Error>, 'enabled'>,
) {
  return useQuery({
    queryKey: getQueryPluginQueryKey(workspace, queryPluginId, params),
    queryFn: () => fetchQueryPlugin<TData>(workspace, queryPluginId, params),
    enabled:
      options?.enabled ??
      Boolean(workspace && queryPluginId && params.experiment_id),
  });
}
