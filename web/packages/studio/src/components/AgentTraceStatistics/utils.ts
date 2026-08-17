// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  TraceStatisticsBucket,
  TraceStatisticsRange,
  TraceStatisticsSample,
  TraceStatisticsSummary,
} from '@studio/components/AgentTraceStatistics/types';

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

export const RANGE_LABELS: Record<TraceStatisticsRange, string> = {
  day: 'Day',
  week: 'Week',
  month: 'Month',
};

/** A day range is too short for daily buckets — it would collapse to a single point. */
export const bucketMsForRange = (range: TraceStatisticsRange): number =>
  range === 'day' ? HOUR_MS : DAY_MS;

export const bucketAdverbForRange = (range: TraceStatisticsRange): string =>
  range === 'day' ? 'Hourly' : 'Daily';

const isFiniteNumber = (value: number | null | undefined): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const mean = (sum: number, count: number): number => (count > 0 ? sum / count : 0);

export const summarizeTraces = (traces: TraceStatisticsSample[]): TraceStatisticsSummary => {
  let latencySum = 0;
  let latencyCount = 0;
  let tokenSum = 0;
  let tokenCount = 0;
  let costSum = 0;
  let costCount = 0;

  for (const trace of traces) {
    // ms/token is only meaningful when the run actually produced tokens.
    if (
      isFiniteNumber(trace.durationMs) &&
      isFiniteNumber(trace.totalTokens) &&
      trace.totalTokens > 0
    ) {
      latencySum += trace.durationMs / trace.totalTokens;
      latencyCount += 1;
    }
    if (isFiniteNumber(trace.totalTokens)) {
      tokenSum += trace.totalTokens;
      tokenCount += 1;
    }
    if (isFiniteNumber(trace.costUsd)) {
      costSum += trace.costUsd;
      costCount += 1;
    }
  }

  return {
    totalTraces: traces.length,
    avgLatencyMsPerToken: mean(latencySum, latencyCount),
    avgTokensPerRun: mean(tokenSum, tokenCount),
    avgCostUsd: mean(costSum, costCount),
  };
};

interface BucketAccumulator {
  costSum: number;
  costCount: number;
  tokenSum: number;
  tokenCount: number;
  latencySum: number;
  latencyCount: number;
}

const emptyAccumulator = (): BucketAccumulator => ({
  costSum: 0,
  costCount: 0,
  tokenSum: 0,
  tokenCount: 0,
  latencySum: 0,
  latencyCount: 0,
});

const average = (sum: number, count: number): number | null => (count > 0 ? sum / count : null);

/**
 * Averages each metric within fixed-width time buckets. Buckets with no traces are emitted as
 * `null` points so the line breaks instead of dipping to zero — a quiet day is missing data, not a
 * day that cost nothing.
 */
export const bucketTraceAverages = (
  traces: TraceStatisticsSample[],
  range: TraceStatisticsRange
): TraceStatisticsBucket[] => {
  const bucketMs = bucketMsForRange(range);
  const buckets = new Map<number, BucketAccumulator>();

  for (const trace of traces) {
    const time = trace.startedAt.getTime();
    if (!Number.isFinite(time)) continue;

    const key = Math.floor(time / bucketMs) * bucketMs;
    const acc = buckets.get(key) ?? emptyAccumulator();
    if (isFiniteNumber(trace.costUsd)) {
      acc.costSum += trace.costUsd;
      acc.costCount += 1;
    }
    if (isFiniteNumber(trace.totalTokens)) {
      acc.tokenSum += trace.totalTokens;
      acc.tokenCount += 1;
    }
    if (isFiniteNumber(trace.durationMs)) {
      acc.latencySum += trace.durationMs;
      acc.latencyCount += 1;
    }
    buckets.set(key, acc);
  }

  if (buckets.size === 0) return [];

  const keys = Array.from(buckets.keys()).sort((a, b) => a - b);
  const points: TraceStatisticsBucket[] = [];
  for (let key = keys[0]; key <= keys[keys.length - 1]; key += bucketMs) {
    const acc = buckets.get(key);
    points.push({
      timestamp: key,
      costUsd: acc ? average(acc.costSum, acc.costCount) : null,
      tokens: acc ? average(acc.tokenSum, acc.tokenCount) : null,
      latencyMs: acc ? average(acc.latencySum, acc.latencyCount) : null,
    });
  }
  return points;
};

export const formatTokens = (value: number): string =>
  Math.round(value).toLocaleString(undefined, { maximumFractionDigits: 0 });

export const formatLatencyMs = (value: number): string =>
  `${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 1 : 0 })} ms`;

export const formatMsPerToken = (value: number): string =>
  value === 0
    ? '0'
    : value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 2 : 0 });

export const formatBucketTick = (timestamp: number, range: TraceStatisticsRange): string => {
  const date = new Date(timestamp);
  return range === 'day'
    ? date.toLocaleTimeString(undefined, { hour: 'numeric' })
    : `${date.getUTCMonth() + 1}/${date.getUTCDate()}`;
};
