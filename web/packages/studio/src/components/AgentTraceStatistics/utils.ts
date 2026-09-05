// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatNumericValue } from '@nemo/common/src/components/charts/format';
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

/**
 * Day buckets start at local midnight, and a DST transition makes consecutive midnights 23 or 25
 * hours apart, so they have to be walked with calendar arithmetic. Hour buckets are evenly spaced
 * in absolute time whatever the offset does, so a fixed step is exact there.
 */
const nextBucketStart = (timestamp: number, range: TraceStatisticsRange): number => {
  if (range === 'day') return timestamp + HOUR_MS;
  const next = new Date(timestamp);
  next.setDate(next.getDate() + 1);
  return next.getTime();
};

export const bucketAdverbForRange = (range: TraceStatisticsRange): string =>
  range === 'day' ? 'Hourly' : 'Daily';

/**
 * Intake only emits buckets that saw runs. Re-inserting the empty ones as `null` points breaks the
 * line instead of dipping it to zero — a quiet day is missing data, not a day that cost nothing.
 *
 * Bucket starts arrive aligned to the browser timezone, so the walk from one bucket to the next
 * follows the local calendar (see `nextBucketStart`) rather than a fixed width — otherwise a DST
 * transition knocks every later step off the real bucket starts and blanks out points that have
 * data.
 */
export const fillBucketGaps = (
  points: TraceStatisticsBucket[],
  range: TraceStatisticsRange
): TraceStatisticsBucket[] => {
  if (points.length === 0) return [];

  const sorted = [...points].sort((a, b) => a.timestamp - b.timestamp);
  const byTimestamp = new Map(sorted.map((point) => [point.timestamp, point]));

  const filled: TraceStatisticsBucket[] = [];
  const last = sorted[sorted.length - 1].timestamp;
  for (
    let timestamp = sorted[0].timestamp;
    timestamp <= last;
    timestamp = nextBucketStart(timestamp, range)
  ) {
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

export const formatTokensCompact = (value: number): string => formatNumericValue(Math.round(value));

export const formatLatencyMsCompact = (value: number): string =>
  Math.abs(value) >= 1000 ? `${formatNumericValue(value)} ms` : formatLatencyMs(value);

/** Buckets are aligned to the browser's timezone, so the tick reads in local time too. */
export const formatBucketTick = (timestamp: number, range: TraceStatisticsRange): string => {
  const date = new Date(timestamp);
  return range === 'day'
    ? date.toLocaleTimeString(undefined, { hour: 'numeric' })
    : `${date.getMonth() + 1}/${date.getDate()}`;
};
