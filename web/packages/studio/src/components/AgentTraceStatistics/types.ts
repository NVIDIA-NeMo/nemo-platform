// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Window the statistics cover. Drives both the header label and the bucket size. */
export type TraceStatisticsRange = 'day' | 'week' | 'month';

/**
 * The subset of `Trace` this component needs. Kept structural rather than importing the SDK type
 * so stories and tests can build fixtures without a full trace payload.
 */
export interface TraceStatisticsSample {
  readonly startedAt: Date;
  readonly durationMs?: number | null;
  readonly totalTokens?: number | null;
  readonly costUsd?: number | null;
}

export interface TraceStatisticsSummary {
  totalTraces: number;
  /** Wall-clock duration divided by tokens produced, averaged per trace. */
  avgLatencyMsPerToken: number;
  avgTokensPerRun: number;
  avgCostUsd: number;
}

/** One point on the trend chart. `null` renders a gap rather than a drop to zero. */
export interface TraceStatisticsBucket {
  /** Bucket start, epoch milliseconds. */
  timestamp: number;
  costUsd: number | null;
  tokens: number | null;
  latencyMs: number | null;
}
