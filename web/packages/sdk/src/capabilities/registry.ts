// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CapabilityMeta } from './types';

/** A lightweight summary returned by search, cheap for an LLM to scan. */
export interface CapabilitySummary {
  readonly name: string;
  readonly service: string;
  readonly method: string;
  readonly path: string;
  readonly summary: string;
  readonly readOnly: boolean;
}

export interface SearchOptions {
  /** Max results to return. Defaults to 25. */
  readonly limit?: number;
  /** Restrict to a single service spec. */
  readonly service?: string;
  /** Restrict to read-only (true) or mutating (false) operations. */
  readonly readOnly?: boolean;
}

const toSummary = (meta: CapabilityMeta): CapabilitySummary => ({
  name: meta.name,
  service: meta.service,
  method: meta.method,
  path: meta.path,
  summary: meta.summary ?? meta.description ?? '',
  readOnly: meta.readOnly,
});

/** Builds an O(1) name → metadata index over a registry. */
export const indexByName = (
  capabilities: readonly CapabilityMeta[]
): ReadonlyMap<string, CapabilityMeta> => new Map(capabilities.map((c) => [c.name, c]));

export const getCapability = (
  capabilities: readonly CapabilityMeta[],
  name: string
): CapabilityMeta | undefined => capabilities.find((c) => c.name === name);

const haystack = (meta: CapabilityMeta): string =>
  [meta.name, meta.path, meta.summary, meta.description, meta.service, ...meta.tags]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

/**
 * Ranked keyword search over the registry. Every whitespace-separated term in
 * `query` must appear somewhere in the operation's name/path/summary/tags. Results
 * are scored by how many terms hit the name or path (the strongest signals) so the
 * most relevant operations surface first.
 */
export const searchCapabilities = (
  capabilities: readonly CapabilityMeta[],
  query: string,
  options: SearchOptions = {}
): CapabilitySummary[] => {
  const { limit, service, readOnly } = options;
  const safeLimit = limit && Number.isInteger(limit) && limit > 0 ? Math.floor(limit) : 25;
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);

  const scored: Array<{ meta: CapabilityMeta; score: number }> = [];
  for (const meta of capabilities) {
    if (service && meta.service !== service) continue;
    if (readOnly !== undefined && meta.readOnly !== readOnly) continue;

    const hay = haystack(meta);
    if (!terms.every((t) => hay.includes(t))) continue;

    const nameOrPath = `${meta.name} ${meta.path}`.toLowerCase();
    const score = terms.reduce((acc, t) => acc + (nameOrPath.includes(t) ? 1 : 0), 0);
    scored.push({ meta, score });
  }

  scored.sort((a, b) => b.score - a.score || a.meta.name.localeCompare(b.meta.name));
  return scored.slice(0, safeLimit).map(({ meta }) => toSummary(meta));
};
