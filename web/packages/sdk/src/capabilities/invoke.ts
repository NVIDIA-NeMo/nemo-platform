// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CapabilityContext, CapabilityMeta, Fetcher } from './types';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const resolveFetcher = (meta: CapabilityMeta, ctx: CapabilityContext): Fetcher => {
  const fetcher = ctx.fetchers[meta.service] ?? ctx.defaultFetcher;
  if (!fetcher) {
    throw new Error(
      `No fetcher registered for service "${meta.service}". Provide ctx.fetchers["${meta.service}"] or ctx.defaultFetcher.`
    );
  }
  return fetcher;
};

/**
 * Invokes an API operation described by {@link CapabilityMeta}.
 *
 * Path parameters are substituted into the path template, query parameters are
 * collected into `params`, and the `body` argument (if any) becomes the request
 * payload. A `{workspace}` path param falls back to `ctx.workspace` when the
 * caller omits it. The actual HTTP call is delegated to the per-service fetcher,
 * so this function never depends on the generated client directly.
 */
export const invokeCapability = async <T = unknown>(
  meta: CapabilityMeta,
  args: unknown,
  ctx: CapabilityContext
): Promise<T> => {
  const input: Record<string, unknown> = isRecord(args) ? args : {};

  let url = meta.path;
  for (const name of meta.pathParams) {
    let value = input[name];
    if ((value === undefined || value === null) && name === 'workspace' && ctx.workspace) {
      value = ctx.workspace;
    }
    if (value === undefined || value === null) {
      throw new Error(`Missing required path parameter "${name}" for ${meta.name}.`);
    }
    url = url.replace(`{${name}}`, encodeURIComponent(String(value)));
  }

  const params: Record<string, unknown> = {};
  for (const name of meta.queryParams) {
    if (input[name] !== undefined) {
      params[name] = input[name];
    }
  }

  const data = meta.hasBody ? input.body : undefined;
  if (meta.hasBody && meta.bodyRequired && data === undefined) {
    throw new Error(`Missing required request body ("body") for ${meta.name}.`);
  }

  const fetcher = resolveFetcher(meta, ctx);
  return fetcher<T>({
    url,
    method: meta.method,
    params: Object.keys(params).length > 0 ? params : undefined,
    data,
    signal: ctx.signal,
  });
};
