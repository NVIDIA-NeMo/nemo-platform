// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * POC client-side store for Experiments mock data. Replaces direct fixture
 * imports so promote/demote actions can mutate state in-session.
 *
 * When the real backend lands, swap this for the generated SDK hooks. The
 * public shape (getCandidate, getCandidates, promote, demote, useCandidates)
 * is what the routes consume — the routes don't reach into fixtures directly.
 */

import { useSyncExternalStore } from 'react';

import {
  type Candidate,
  type DatasetSlice,
  CANDIDATES as CANDIDATE_FIXTURES,
  DATASETS,
} from './fixtures';

let candidates: Candidate[] = CANDIDATE_FIXTURES.map((c) => ({ ...c }));
let listeners: Array<() => void> = [];

const subscribe = (listener: () => void) => {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
};

const getSnapshot = () => candidates;
const notify = () => {
  listeners.forEach((l) => l());
};

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export interface PromoteInput {
  slug: string;
  name: string;
  description?: string;
  promoted_via?: 'auto' | 'manual';
  promoted_by?: string;
}

export interface PromoteResult {
  promoted: Candidate;
  demoted?: Candidate;
}

/**
 * Atomic promotion: if another Benchmark exists for the same
 * (agent_name, dataset_id), demote it. Then promote the target.
 *
 * Throws if slug conflicts with another Benchmark in the workspace (not the
 * one being demoted).
 */
export const promoteCandidate = (candidateId: string, input: PromoteInput): PromoteResult => {
  const target = candidates.find((c) => c.candidate_id === candidateId);
  if (!target) {
    throw new Error(`Candidate ${candidateId} not found`);
  }

  // Slug uniqueness check (excluding the candidate to be demoted, if any).
  const conflicting = candidates.find(
    (c) =>
      c.is_benchmark &&
      c.benchmark_slug === input.slug &&
      c.candidate_id !== candidateId &&
      !(c.agent_name === target.agent_name && c.dataset_id === target.dataset_id),
  );
  if (conflicting) {
    throw new Error(`Benchmark slug "${input.slug}" is already in use.`);
  }

  // Find and demote the current Benchmark for this (agent, dataset) pair, if any.
  const currentBenchmark = candidates.find(
    (c) =>
      c.is_benchmark &&
      c.agent_name === target.agent_name &&
      c.dataset_id === target.dataset_id &&
      c.candidate_id !== candidateId,
  );

  const now = new Date().toISOString();

  candidates = candidates.map((c) => {
    if (c.candidate_id === currentBenchmark?.candidate_id) {
      return {
        ...c,
        is_benchmark: false,
        benchmark_slug: undefined,
        benchmark_name: undefined,
        benchmark_description: undefined,
        benchmark_promoted_at: undefined,
        benchmark_promoted_via: undefined,
        benchmark_promoted_by: undefined,
      };
    }
    if (c.candidate_id === candidateId) {
      return {
        ...c,
        is_benchmark: true,
        benchmark_slug: input.slug,
        benchmark_name: input.name,
        benchmark_description: input.description,
        benchmark_promoted_at: now,
        benchmark_promoted_via: input.promoted_via ?? 'manual',
        benchmark_promoted_by: input.promoted_by ?? 'sbuggy@nvidia.com',
      };
    }
    return c;
  });

  notify();
  return {
    promoted: candidates.find((c) => c.candidate_id === candidateId) as Candidate,
    demoted: currentBenchmark,
  };
};

export const demoteCandidate = (candidateId: string): Candidate | undefined => {
  const target = candidates.find((c) => c.candidate_id === candidateId);
  if (!target || !target.is_benchmark) {
    return undefined;
  }

  candidates = candidates.map((c) => {
    if (c.candidate_id !== candidateId) {
      return c;
    }
    return {
      ...c,
      is_benchmark: false,
      benchmark_slug: undefined,
      benchmark_name: undefined,
      benchmark_description: undefined,
      benchmark_promoted_at: undefined,
      benchmark_promoted_via: undefined,
      benchmark_promoted_by: undefined,
    };
  });

  notify();
  return candidates.find((c) => c.candidate_id === candidateId);
};

// ---------------------------------------------------------------------------
// Read hooks / helpers
// ---------------------------------------------------------------------------

export const useCandidates = (): Candidate[] => useSyncExternalStore(subscribe, getSnapshot);

export const useCandidate = (candidateId: string | undefined): Candidate | undefined => {
  const all = useCandidates();
  if (!candidateId) {
    return undefined;
  }
  return all.find((c) => c.candidate_id === candidateId);
};

export const getCurrentBenchmark = (
  candidates: Candidate[],
  agentName: string,
  datasetId: string,
): Candidate | undefined =>
  candidates.find(
    (c) => c.is_benchmark && c.agent_name === agentName && c.dataset_id === datasetId,
  );

export const getAllCurrentBenchmarks = (candidates: Candidate[]): Candidate[] =>
  candidates.filter((c) => c.is_benchmark);

/**
 * Unique (agent, dataset) tuples represented by any Candidate in the
 * workspace. Powers the Benchmarks page's "row per tuple" view, including
 * empty-state for tuples that have Candidates but no Benchmark yet.
 */
export interface AgentDatasetTuple {
  agent_name: string;
  dataset_id: string;
  dataset_version?: string;
  dataset_name: string;
  candidate_count: number;
}

export const getAllAgentDatasetTuples = (candidates: Candidate[]): AgentDatasetTuple[] => {
  const seen = new Map<string, AgentDatasetTuple>();
  for (const candidate of candidates) {
    const key = `${candidate.agent_name}::${candidate.dataset_id}`;
    const existing = seen.get(key);
    if (existing) {
      existing.candidate_count += 1;
    } else {
      const meta = Object.values(DATASETS).find((d) => d.id === candidate.dataset_id);
      seen.set(key, {
        agent_name: candidate.agent_name,
        dataset_id: candidate.dataset_id,
        dataset_version: candidate.dataset_version,
        dataset_name: meta?.name ?? candidate.dataset_id,
        candidate_count: 1,
      });
    }
  }
  return Array.from(seen.values());
};

// Re-export shared types for convenience so callers only import from one place.
export type { Candidate, DatasetSlice };
