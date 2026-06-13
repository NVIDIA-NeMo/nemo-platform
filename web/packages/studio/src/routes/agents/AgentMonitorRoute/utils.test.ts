// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunSummary } from '@studio/routes/agents/AgentMonitorRoute/telemetry';
import {
  bucketTokensByTime,
  isNotFoundError,
  sampleNewestPerAgent,
  summarizeRuns,
} from '@studio/routes/agents/AgentMonitorRoute/utils';

const makeRun = (overrides: Partial<RunSummary> = {}): RunSummary => ({
  runId: overrides.runId ?? 'r',
  agent: overrides.agent,
  startedAt: overrides.startedAt ?? new Date('2026-01-01T00:00:00Z'),
  endedAt: overrides.endedAt ?? new Date('2026-01-01T00:00:01Z'),
  durationMs: overrides.durationMs ?? 1000,
  model: overrides.model,
  inputPreview: overrides.inputPreview ?? '',
  outputPreview: overrides.outputPreview ?? '',
  promptTokens: overrides.promptTokens ?? 0,
  completionTokens: overrides.completionTokens ?? 0,
  toolCalls: overrides.toolCalls ?? 0,
});

describe('isNotFoundError', () => {
  it('matches axios-shaped 404s and bare-status 404s', () => {
    expect(isNotFoundError({ response: { status: 404 } })).toBe(true);
    expect(isNotFoundError({ status: 404 })).toBe(true);
  });

  it('rejects other shapes', () => {
    expect(isNotFoundError({ response: { status: 500 } })).toBe(false);
    expect(isNotFoundError({ status: 200 })).toBe(false);
    expect(isNotFoundError(null)).toBe(false);
    expect(isNotFoundError(new Error('boom'))).toBe(false);
  });
});

describe('sampleNewestPerAgent', () => {
  it('round-robins newest-first per agent so no single agent crowds out others', () => {
    const files = [
      { path: 'agent-z/runs/2026-01-01-old/part-0.jsonl' },
      { path: 'agent-z/runs/2026-01-02-old/part-0.jsonl' },
      { path: 'agent-z/runs/2026-01-05-newest/part-0.jsonl' },
      { path: 'agent-a/runs/2026-01-04-recent/part-0.jsonl' },
    ];
    const sampled = sampleNewestPerAgent(files, 4);
    expect(sampled.map((f) => f.path)).toEqual([
      // Round 0: each agent's newest file (Map insertion order = first-seen)
      'agent-z/runs/2026-01-05-newest/part-0.jsonl',
      'agent-a/runs/2026-01-04-recent/part-0.jsonl',
      // Round 1: each agent's next-newest
      'agent-z/runs/2026-01-02-old/part-0.jsonl',
      'agent-z/runs/2026-01-01-old/part-0.jsonl',
    ]);
  });

  it('honors the limit and stops when no agent has more files', () => {
    const files = [
      { path: 'a/runs/r1/p.jsonl' },
      { path: 'a/runs/r2/p.jsonl' },
      { path: 'b/runs/r3/p.jsonl' },
    ];
    expect(sampleNewestPerAgent(files, 2)).toHaveLength(2);
    expect(sampleNewestPerAgent(files, 50)).toHaveLength(3);
  });
});

describe('summarizeRuns', () => {
  it('aggregates totals, averages, and finds the most-used model', () => {
    const runs = [
      makeRun({
        runId: '1',
        agent: 'a',
        model: 'mistral-7b',
        promptTokens: 10,
        completionTokens: 4,
        toolCalls: 1,
      }),
      makeRun({
        runId: '2',
        agent: 'a',
        model: 'mistral-7b',
        promptTokens: 30,
        completionTokens: 6,
        toolCalls: 2,
      }),
      makeRun({
        runId: '3',
        agent: 'b',
        model: 'llama-70b',
        promptTokens: 20,
        completionTokens: 10,
        toolCalls: 0,
      }),
    ];
    const summary = summarizeRuns(runs);
    expect(summary).toMatchObject({
      totalRuns: 3,
      avgPromptTokens: 20,
      avgCompletionTokens: 7, // (4+6+10)/3 = 6.67 → rounds to 7
      totalToolCalls: 3,
      topModel: 'mistral-7b',
      topModelCount: 2,
      uniqueModels: 2,
      uniqueAgents: 2,
    });
  });

  it('returns zeros and an em-dash topModel when there are no runs', () => {
    expect(summarizeRuns([])).toMatchObject({
      totalRuns: 0,
      avgPromptTokens: 0,
      avgCompletionTokens: 0,
      totalToolCalls: 0,
      topModel: '—',
      topModelCount: 0,
      uniqueModels: 0,
      uniqueAgents: 0,
    });
  });
});

describe('bucketTokensByTime', () => {
  it('chooses a 5-minute bucket for spans under 2h and groups tokens into it', () => {
    const t0 = new Date('2026-01-01T00:00:00Z');
    const t1 = new Date('2026-01-01T00:03:00Z'); // same 5-min bucket
    const t2 = new Date('2026-01-01T00:06:00Z'); // next bucket
    const result = bucketTokensByTime([
      makeRun({ runId: '1', startedAt: t0, promptTokens: 10, completionTokens: 5 }),
      makeRun({ runId: '2', startedAt: t1, promptTokens: 4, completionTokens: 1 }),
      makeRun({ runId: '3', startedAt: t2, promptTokens: 1, completionTokens: 1 }),
    ]);
    expect(result.bucketMs).toBe(5 * 60 * 1000);
    expect(result.timestamps).toHaveLength(2);
    expect(result.promptTokens).toEqual([14, 1]);
    expect(result.completionTokens).toEqual([6, 1]);
  });

  it('escalates to daily buckets for spans longer than a week', () => {
    const t0 = new Date('2026-01-01T00:00:00Z');
    const t1 = new Date('2026-01-15T00:00:00Z');
    const result = bucketTokensByTime([
      makeRun({ runId: '1', startedAt: t0 }),
      makeRun({ runId: '2', startedAt: t1 }),
    ]);
    expect(result.bucketMs).toBe(24 * 60 * 60 * 1000);
  });
});
