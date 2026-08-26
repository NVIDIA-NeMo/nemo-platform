// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { toRecentExperiments } from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

interface EvalOptions {
  experimentId?: string;
  /** Further experiments the evaluation also belongs to, all shown over time and not favorited. */
  alsoInExperimentIds?: string[];
  isFavorite?: boolean;
  showsEvaluationsOverTime?: boolean;
  experimentName?: string | null;
  experimentDescription?: string | null;
  createdAt?: string;
  scores?: Record<string, number>;
}

const evaluation = (name: string, options: EvalOptions = {}): AgentEvaluationRow =>
  ({
    id: `eval-${name}`,
    name,
    workspace: 'default',
    experiment_ids: [options.experimentId ?? 'exp-1', ...(options.alsoInExperimentIds ?? [])],
    dataset_name: 'dataset',
    experiments: [
      {
        id: options.experimentId ?? 'exp-1',
        name: options.experimentName ?? 'Primary use cases',
        description: options.experimentDescription ?? 'Every merge to main.',
        isFavorite: options.isFavorite ?? false,
        showsEvaluationsOverTime: options.showsEvaluationsOverTime ?? true,
      },
      ...(options.alsoInExperimentIds ?? []).map((id) => ({
        id,
        name: id,
        description: null,
        isFavorite: false,
        showsEvaluationsOverTime: true,
      })),
    ],
    created_at: options.createdAt ?? '2026-08-01T00:00:00Z',
    aggregate_scores: Object.fromEntries(
      Object.entries(options.scores ?? {}).map(([key, mean]) => [key, { mean }])
    ),
  }) as AgentEvaluationRow;

describe('toRecentExperiments', () => {
  it('rolls evaluations up into one card per experiment, newest first', () => {
    const { recent: result } = toRecentExperiments([
      evaluation('b', { experimentId: 'exp-2', createdAt: '2026-08-10T00:00:00Z' }),
      evaluation('a', { experimentId: 'exp-1', createdAt: '2026-08-05T00:00:00Z' }),
      evaluation('a2', { experimentId: 'exp-1', createdAt: '2026-08-01T00:00:00Z' }),
    ]);

    expect(result.map((row) => row.id)).toEqual(['exp-2', 'exp-1']);
    expect(result[1]?.evaluationCount).toBe(2);
    expect(result[0]?.description).toBe('Every merge to main.');
  });

  it('orders each series oldest-first regardless of the order evaluations arrive in', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('newest', { createdAt: '2026-08-10T00:00:00Z', scores: { solved: 0.6 } }),
      evaluation('oldest', { createdAt: '2026-08-01T00:00:00Z', scores: { solved: 0.2 } }),
    ]);

    expect(experiment?.series[0]?.points.map((point) => point.value)).toEqual([0.2, 0.6]);
    expect(experiment?.series[0]?.value).toBe(0.6);
  });

  it('measures the delta against the newest score at least a week old, as a percent change', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('latest', { createdAt: '2026-08-20T00:00:00Z', scores: { solved: 0.5 } }),
      // Inside the window — must not be used as the baseline.
      evaluation('recent', { createdAt: '2026-08-18T00:00:00Z', scores: { solved: 0.4 } }),
      evaluation('week-ago', { createdAt: '2026-08-13T00:00:00Z', scores: { solved: 0.2 } }),
      evaluation('older', { createdAt: '2026-08-01T00:00:00Z', scores: { solved: 0.1 } }),
    ]);

    // .2 → .5 is a 150% increase, not a raw +0.3.
    expect(experiment?.series[0]?.delta).toBeCloseTo(150);
  });

  it('reports a drop as a negative percent change', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('latest', { createdAt: '2026-08-20T00:00:00Z', scores: { solved: 0.4 } }),
      evaluation('baseline', { createdAt: '2026-08-01T00:00:00Z', scores: { solved: 0.5 } }),
    ]);

    expect(experiment?.series[0]?.delta).toBeCloseTo(-20);
  });

  it('scales the percent change independently of the score magnitude', () => {
    const asPercent = (from: number, to: number) =>
      toRecentExperiments([
        evaluation('latest', { createdAt: '2026-08-20T00:00:00Z', scores: { m: to } }),
        evaluation('baseline', { createdAt: '2026-08-01T00:00:00Z', scores: { m: from } }),
      ]).recent[0]?.series[0]?.delta;

    // A 10% move reads the same whether the metric is a ratio, a point count, or a latency.
    expect(asPercent(0.5, 0.55)).toBeCloseTo(10);
    expect(asPercent(50, 55)).toBeCloseTo(10);
    expect(asPercent(1200, 1320)).toBeCloseTo(10);
  });

  it('omits the delta when the baseline is zero, which has no percent change', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('latest', { createdAt: '2026-08-20T00:00:00Z', scores: { solved: 0.4 } }),
      evaluation('baseline', { createdAt: '2026-08-01T00:00:00Z', scores: { solved: 0 } }),
    ]);

    expect(experiment?.series[0]?.delta).toBeUndefined();
  });

  it('omits the delta when nothing is old enough to compare against', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('latest', { createdAt: '2026-08-20T00:00:00Z', scores: { solved: 0.5 } }),
      evaluation('recent', { createdAt: '2026-08-19T00:00:00Z', scores: { solved: 0.4 } }),
    ]);

    expect(experiment?.series[0]?.delta).toBeUndefined();
  });

  it('builds one alphabetized series per evaluator and humanizes the label', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('a', { scores: { 'llm-judge.tool_use': 0.9, helpfulness: 0.5 } }),
    ]);

    expect(experiment?.series.map((series) => series.label)).toEqual(['Helpfulness', 'Tool Use']);
  });

  it('drops evaluations with no timestamp from the series but still counts them', () => {
    const {
      recent: [experiment],
    } = toRecentExperiments([
      evaluation('dated', { createdAt: '2026-08-01T00:00:00Z', scores: { solved: 0.5 } }),
      { ...evaluation('undated', { scores: { solved: 0.9 } }), created_at: undefined },
    ]);

    expect(experiment?.evaluationCount).toBe(2);
    expect(experiment?.series[0]?.points).toHaveLength(1);
    expect(experiment?.series[0]?.value).toBe(0.5);
  });

  it('ignores evaluations that belong to no experiment', () => {
    expect(
      toRecentExperiments([{ ...evaluation('orphan'), experiment_ids: [], experiments: [] }]).recent
    ).toEqual([]);
  });

  it('counts an evaluation toward every experiment it belongs to, not just the first', () => {
    const { recent } = toRecentExperiments([
      evaluation('shared', {
        experimentId: 'exp-1',
        alsoInExperimentIds: ['exp-2'],
        createdAt: '2026-08-01T00:00:00Z',
        scores: { solved: 0.4 },
      }),
      evaluation('exp-2-only', {
        experimentId: 'exp-2',
        experimentName: 'exp-2',
        createdAt: '2026-08-05T00:00:00Z',
        scores: { solved: 0.6 },
      }),
    ]);

    expect(recent.map((row) => row.id)).toEqual(['exp-2', 'exp-1']);
    // The shared evaluation contributes a card, a count, and a trend point to both experiments.
    expect(recent.map((row) => row.evaluationCount)).toEqual([2, 1]);
    expect(recent[0]?.series[0]?.points.map((point) => point.value)).toEqual([0.4, 0.6]);
  });

  it('keeps an experiment shown over time even when a sibling membership is not', () => {
    const { recent } = toRecentExperiments([
      {
        ...evaluation('shared', { scores: { solved: 0.4 } }),
        experiment_ids: ['exp-hidden', 'exp-shown'],
        experiments: [
          {
            id: 'exp-hidden',
            name: 'Hidden',
            description: null,
            isFavorite: false,
            showsEvaluationsOverTime: false,
          },
          {
            id: 'exp-shown',
            name: 'Shown',
            description: null,
            isFavorite: false,
            showsEvaluationsOverTime: true,
          },
        ],
      },
    ]);

    expect(recent.map((row) => row.id)).toEqual(['exp-shown']);
  });

  it('caps the number of cards', () => {
    const rows = ['exp-1', 'exp-2', 'exp-3', 'exp-4'].map((id, index) =>
      evaluation(id, { experimentId: id, createdAt: `2026-08-0${index + 1}T00:00:00Z` })
    );

    expect(toRecentExperiments(rows).recent).toHaveLength(3);
  });

  it('groups favorites separately from the recent experiments', () => {
    const { favorites, recent } = toRecentExperiments([
      evaluation('a', { experimentId: 'exp-1', createdAt: '2026-08-01T00:00:00Z' }),
      evaluation('b', {
        experimentId: 'exp-2',
        createdAt: '2026-08-05T00:00:00Z',
        isFavorite: true,
      }),
    ]);

    expect(favorites.map((row) => row.id)).toEqual(['exp-2']);
    expect(recent.map((row) => row.id)).toEqual(['exp-1']);
  });

  it('caps each group independently, so favorites never crowd out the recent ones', () => {
    const rows = ['exp-1', 'exp-2', 'exp-3', 'exp-4'].map((id, index) =>
      evaluation(id, {
        experimentId: id,
        createdAt: `2026-08-0${index + 1}T00:00:00Z`,
        isFavorite: true,
      })
    );
    rows.push(evaluation('exp-5', { experimentId: 'exp-5', createdAt: '2026-08-09T00:00:00Z' }));

    const { favorites, recent } = toRecentExperiments(rows);

    expect(favorites).toHaveLength(3);
    expect(recent.map((row) => row.id)).toEqual(['exp-5']);
  });

  it('omits experiments that are not marked to show evaluations over time', () => {
    const { favorites, recent } = toRecentExperiments([
      evaluation('a', { experimentId: 'exp-1', showsEvaluationsOverTime: false }),
      evaluation('b', {
        experimentId: 'exp-2',
        showsEvaluationsOverTime: false,
        isFavorite: true,
      }),
    ]);

    expect(favorites).toEqual([]);
    expect(recent).toEqual([]);
  });
});
