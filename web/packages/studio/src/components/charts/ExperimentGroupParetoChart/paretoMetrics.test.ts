// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  buildParetoPoints,
  deriveParetoMetrics,
  type ParetoMetric,
} from '@studio/components/charts/ExperimentGroupParetoChart/paretoMetrics';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';

// Only the fields the Pareto accessors read (name + cost/latency/evaluator rollup means) are set;
// the rest of the rich EvaluationRow shape is irrelevant here, so build a minimal stand-in.
const point = (opts: {
  name: string;
  cost?: number;
  latency?: number;
  evaluators?: Record<string, number>;
}): EvaluationRow =>
  ({
    name: opts.name,
    id: opts.name,
    cost_usd: opts.cost == null ? undefined : { mean: opts.cost },
    latency_ms: opts.latency == null ? undefined : { mean: opts.latency },
    aggregate_scores: opts.evaluators
      ? Object.fromEntries(Object.entries(opts.evaluators).map(([name, mean]) => [name, { mean }]))
      : undefined,
  }) as unknown as EvaluationRow;

const getMetric = (metrics: ParetoMetric[], id: string): ParetoMetric => {
  const metric = metrics.find((m) => m.id === id);
  if (!metric) throw new Error(`metric ${id} not found`);
  return metric;
};

const frontierNames = (points: EvaluationRow[], x: ParetoMetric, y: ParetoMetric): string[] =>
  buildParetoPoints(points, x, y)
    .filter((p) => p.onFrontier)
    .map((p) => p.name)
    .sort();

describe('deriveParetoMetrics', () => {
  it('always offers cost and latency (minimized) plus one option per evaluator (maximized)', () => {
    const points = [point({ name: 'a', evaluators: { reward: 1, safety: 1 } })];
    const metrics = deriveParetoMetrics(points);
    // Evaluator ids use the API vocabulary (`evaluators.<name>`) so they match the group's saved axes.
    expect(metrics.map((m) => m.id)).toEqual([
      'cost_usd',
      'latency_ms',
      'evaluators.reward',
      'evaluators.safety',
    ]);
    expect(getMetric(metrics, 'cost_usd').direction).toBe('min');
    expect(getMetric(metrics, 'latency_ms').direction).toBe('min');
    expect(getMetric(metrics, 'evaluators.reward').direction).toBe('max');
  });

  it('offers only cost and latency when no evaluators are present', () => {
    expect(deriveParetoMetrics([point({ name: 'a' })]).map((m) => m.id)).toEqual([
      'cost_usd',
      'latency_ms',
    ]);
  });
});

describe('buildParetoPoints', () => {
  it('marks the non-dominated set for two minimized axes (cost vs latency)', () => {
    const points = [
      point({ name: 'A', cost: 1, latency: 4 }), // cheapest -> frontier
      point({ name: 'B', cost: 2, latency: 2 }), // balanced -> frontier
      point({ name: 'C', cost: 4, latency: 1 }), // fastest -> frontier
      point({ name: 'D', cost: 3, latency: 3 }), // dominated by B
    ];
    const metrics = deriveParetoMetrics(points);
    expect(
      frontierNames(points, getMetric(metrics, 'cost_usd'), getMetric(metrics, 'latency_ms'))
    ).toEqual(['A', 'B', 'C']);
  });

  it('respects mixed directions: minimize cost, maximize an evaluator score', () => {
    const points = [
      point({ name: 'A', cost: 1, evaluators: { reward: 0.5 } }), // cheapest -> frontier
      point({ name: 'B', cost: 2, evaluators: { reward: 0.9 } }), // most accurate -> frontier
      point({ name: 'C', cost: 2, evaluators: { reward: 0.4 } }), // dominated by A
    ];
    const metrics = deriveParetoMetrics(points);
    expect(
      frontierNames(points, getMetric(metrics, 'cost_usd'), getMetric(metrics, 'evaluators.reward'))
    ).toEqual(['A', 'B']);
  });

  it('drops points missing either selected metric', () => {
    const points = [
      point({ name: 'A', cost: 1, latency: 1 }),
      point({ name: 'B', cost: 2 }), // no latency -> excluded
    ];
    const metrics = deriveParetoMetrics(points);
    const plotted = buildParetoPoints(
      points,
      getMetric(metrics, 'cost_usd'),
      getMetric(metrics, 'latency_ms')
    );
    expect(plotted.map((p) => p.name)).toEqual(['A']);
  });
});
