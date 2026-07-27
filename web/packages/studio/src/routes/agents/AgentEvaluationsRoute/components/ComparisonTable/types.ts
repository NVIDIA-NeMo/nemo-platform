// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvaluateJob } from '@nemo/sdk/generated/evaluator/schema';
import {
  agentNameForJob,
  aggregateScoresOf,
  evalConfigName,
  type AgentEvalAggregateScore,
  type AgentEvalResult,
} from '@studio/api/evaluation/agent-evaluations';

/** A completed evaluation run, represented in the common shape consumed by comparison views.
 * All entries passed to a comparison component must use the same persisted eval config. */
export interface ComparisonEntry {
  id: string;
  label: string;
  agentName: string | null;
  evaluationName: string;
  createdAt: string | null;
  scores: readonly AgentEvalAggregateScore[];
}

/** The expected range for a score. Supplying bounds keeps radar axes meaningful for scores
 * whose scale is not the usual 0–1 range. */
export interface ComparisonMetricBounds {
  min: number;
  max: number;
}

/** Creates comparison rows from evaluator API responses and keeps only runs tied to one
 * persisted eval-config fileset. `resultsByJobName` is the map returned by
 * `fetchAgentEvalResultsForJobs`. */
export const comparisonsForEvalConfig = (
  jobs: readonly AgentEvaluateJob[],
  resultsByJobName: ReadonlyMap<string, AgentEvalResult>,
  configName: string
): ComparisonEntry[] =>
  jobs.flatMap((job) => {
    if (evalConfigName(job) !== configName || !job.name) return [];
    const agentName = agentNameForJob(job);
    return [
      {
        id: job.id || job.name,
        label: agentName ?? job.name,
        agentName,
        evaluationName: job.name,
        createdAt: job.created_at ?? null,
        scores: aggregateScoresOf(resultsByJobName.get(job.name) ?? null),
      },
    ];
  });

export const metricNamesForComparisons = (entries: readonly ComparisonEntry[]): string[] =>
  Array.from(new Set(entries.flatMap((entry) => entry.scores.map((score) => score.name))));

export const scoreForMetric = (entry: ComparisonEntry, metricName: string): number | null => {
  const score = entry.scores.find((candidate) => candidate.name === metricName)?.mean;
  return typeof score === 'number' && Number.isFinite(score) ? score : null;
};

/** One metric's value in a non-baseline run, alongside the baseline it is measured against. */
export interface ComparisonMetricDelta {
  value: number | null;
  baselineValue: number | null;
  /** `value - baselineValue`, or null when either side has no score. */
  difference: number | null;
}

/** The run every other run is compared against. Callers control this by ordering the list. */
export const baselineForComparisons = (
  entries: readonly ComparisonEntry[]
): ComparisonEntry | null => entries[0] ?? null;

/** Every run after the baseline, in the order supplied. */
export const candidatesForComparisons = (entries: readonly ComparisonEntry[]): ComparisonEntry[] =>
  entries.slice(1);

export const deltaFromBaseline = (
  entry: ComparisonEntry,
  baseline: ComparisonEntry | null,
  metricName: string
): ComparisonMetricDelta => {
  const value = scoreForMetric(entry, metricName);
  const baselineValue = baseline ? scoreForMetric(baseline, metricName) : null;
  return {
    value,
    baselineValue,
    difference: value !== null && baselineValue !== null ? value - baselineValue : null,
  };
};

/** Converts a metric value into a 0–1 chart value. Missing values remain null so callers can
 * make their missing-data policy explicit. */
export const normalizeScore = (
  value: number | null,
  bounds: ComparisonMetricBounds | undefined
): number | null => {
  if (value === null) return null;
  const min = bounds?.min ?? 0;
  const max = bounds?.max ?? 1;
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
};
