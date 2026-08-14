// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TraceStatisticsSample } from '@studio/components/AgentTraceStatistics/types';
import {
  bucketTraceAverages,
  formatCostUsd,
  summarizeTraces,
} from '@studio/components/AgentTraceStatistics/utils';

const at = (
  iso: string,
  overrides: Partial<TraceStatisticsSample> = {}
): TraceStatisticsSample => ({
  startedAt: new Date(iso),
  durationMs: 1000,
  totalTokens: 100,
  costUsd: 0.01,
  ...overrides,
});

describe('summarizeTraces', () => {
  it('returns zeros for no traces', () => {
    expect(summarizeTraces([])).toEqual({
      totalTraces: 0,
      avgLatencyMsPerToken: 0,
      avgTokensPerRun: 0,
      avgCostUsd: 0,
    });
  });

  it('averages latency per token rather than dividing the totals', () => {
    const summary = summarizeTraces([
      at('2026-07-01T00:00:00Z', { durationMs: 1000, totalTokens: 100 }),
      at('2026-07-01T01:00:00Z', { durationMs: 600, totalTokens: 200 }),
    ]);
    // (10 + 3) / 2, not 1600 / 300.
    expect(summary.avgLatencyMsPerToken).toBeCloseTo(6.5);
    expect(summary.avgTokensPerRun).toBe(150);
    expect(summary.totalTraces).toBe(2);
  });

  it('skips traces missing a metric instead of counting them as zero', () => {
    const summary = summarizeTraces([
      at('2026-07-01T00:00:00Z', { costUsd: 0.04 }),
      at('2026-07-01T01:00:00Z', { costUsd: null }),
    ]);
    expect(summary.avgCostUsd).toBeCloseTo(0.04);
    expect(summary.totalTraces).toBe(2);
  });

  it('ignores zero-token traces when averaging ms/tok', () => {
    const summary = summarizeTraces([
      at('2026-07-01T00:00:00Z', { durationMs: 1000, totalTokens: 100 }),
      at('2026-07-01T01:00:00Z', { durationMs: 500, totalTokens: 0 }),
    ]);
    expect(summary.avgLatencyMsPerToken).toBeCloseTo(10);
  });
});

describe('bucketTraceAverages', () => {
  it('averages within a day bucket', () => {
    const buckets = bucketTraceAverages(
      [
        at('2026-07-01T02:00:00Z', { totalTokens: 100 }),
        at('2026-07-01T20:00:00Z', { totalTokens: 300 }),
      ],
      'week'
    );
    expect(buckets).toHaveLength(1);
    expect(buckets[0].tokens).toBe(200);
  });

  it('emits null for gaps so the line breaks rather than dipping to zero', () => {
    const buckets = bucketTraceAverages(
      [at('2026-07-01T02:00:00Z'), at('2026-07-04T02:00:00Z')],
      'week'
    );
    expect(buckets).toHaveLength(4);
    expect(buckets[1].tokens).toBeNull();
    expect(buckets[2].tokens).toBeNull();
    expect(buckets[3].tokens).toBe(100);
  });

  it('uses hourly buckets for the day range', () => {
    const buckets = bucketTraceAverages(
      [at('2026-07-01T02:10:00Z'), at('2026-07-01T04:10:00Z')],
      'day'
    );
    expect(buckets).toHaveLength(3);
  });

  it('returns no points for no traces', () => {
    expect(bucketTraceAverages([], 'month')).toEqual([]);
  });
});

describe('formatCostUsd', () => {
  it('keeps sub-cent averages readable', () => {
    expect(formatCostUsd(0.0072)).toBe('$0.0072');
    expect(formatCostUsd(1.5)).toBe('$1.50');
    expect(formatCostUsd(0)).toBe('$0');
  });
});
