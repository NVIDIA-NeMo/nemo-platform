// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TraceMetricBucketParam } from '@nemo/sdk/generated/platform/schema';
import type {
  TraceStatisticsBucket,
  TraceStatisticsRange,
} from '@studio/components/AgentTraceStatistics/types';

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

export const RANGE_LABELS: Record<TraceStatisticsRange, string> = {
  day: 'Day',
  week: 'Week',
  month: 'Month',
};

/** A day range is too short for daily buckets — it would collapse to a single point. */
export const bucketParamForRange = (range: TraceStatisticsRange): TraceMetricBucketParam =>
  range === 'day' ? 'hour' : 'day';

export const bucketMsForRange = (range: TraceStatisticsRange): number =>
  range === 'day' ? HOUR_MS : DAY_MS;

export const bucketAdverbForRange = (range: TraceStatisticsRange): string =>
  range === 'day' ? 'Hourly' : 'Daily';

/**
 * Intake only emits buckets that saw runs. Re-inserting the empty ones as `null` points breaks the
 * line instead of dipping it to zero — a quiet day is missing data, not a day that cost nothing.
 *
 * Bucket starts arrive aligned to the requested timezone, so stepping by a fixed width is exact for
 * hour and day buckets. A DST transition shifts a day boundary by an hour; the resulting point
 * lands within the same bucket, so the series stays in order.
 */
export const fillBucketGaps = (
  points: TraceStatisticsBucket[],
  range: TraceStatisticsRange
): TraceStatisticsBucket[] => {
  if (points.length === 0) return [];

  const bucketMs = bucketMsForRange(range);
  const sorted = [...points].sort((a, b) => a.timestamp - b.timestamp);
  const byTimestamp = new Map(sorted.map((point) => [point.timestamp, point]));

  const filled: TraceStatisticsBucket[] = [];
  const last = sorted[sorted.length - 1].timestamp;
  for (let timestamp = sorted[0].timestamp; timestamp <= last; timestamp += bucketMs) {
    filled.push(
      byTimestamp.get(timestamp) ?? { timestamp, costUsd: null, tokens: null, latencyMs: null }
    );
  }
  return filled;
};

export const formatTokens = (value: number): string =>
  Math.round(value).toLocaleString(undefined, { maximumFractionDigits: 0 });

export const formatLatencyMs = (value: number): string =>
  `${value.toLocaleString(undefined, { maximumFractionDigits: value < 10 ? 1 : 0 })} ms`;

/** Buckets are aligned to the browser's timezone, so the tick reads in local time too. */
export const formatBucketTick = (timestamp: number, range: TraceStatisticsRange): string => {
  const date = new Date(timestamp);
  return range === 'day'
    ? date.toLocaleTimeString(undefined, { hour: 'numeric' })
    : `${date.getMonth() + 1}/${date.getDate()}`;
};
