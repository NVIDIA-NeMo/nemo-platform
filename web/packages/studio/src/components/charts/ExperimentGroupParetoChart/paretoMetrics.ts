// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ParetoMetricPoint } from '@nemo/sdk/generated/platform/schema';

/** Which direction on an axis counts as "better": cost/latency minimize, evaluator scores maximize. */
export type MetricDirection = 'min' | 'max';

export interface ParetoMetric {
  /**
   * Stable id, using the same metric vocabulary the API stores in `group.pareto` and the list
   * sort/filter fields: `cost_usd`, `latency_ms`, or `evaluators.<name>`.
   */
  readonly id: string;
  readonly label: string;
  readonly direction: MetricDirection;
  readonly accessor: (point: ParetoMetricPoint) => number | null | undefined;
}

const capitalize = (value: string): string =>
  value ? value.charAt(0).toUpperCase() + value.slice(1) : value;

/**
 * The display label for a metric id, resolvable synchronously from the id alone (no loaded points
 * needed): `cost_usd` -> "Cost (USD)", `latency_ms` -> "Latency (ms)", `evaluators.<name>` -> the
 * capitalized evaluator name. Used so a saved evaluator axis renders its real label immediately
 * instead of flashing the cost/latency fallback while the chart data loads.
 */
export function metricLabel(id: string): string {
  if (id === 'cost_usd') return 'Cost (USD)';
  if (id === 'latency_ms') return 'Latency (ms)';
  return capitalize(id.startsWith('evaluators.') ? id.slice('evaluators.'.length) : id);
}

const COST_METRIC: ParetoMetric = {
  id: 'cost_usd',
  label: metricLabel('cost_usd'),
  direction: 'min',
  accessor: (point) => point.cost_usd,
};

const LATENCY_METRIC: ParetoMetric = {
  id: 'latency_ms',
  label: metricLabel('latency_ms'),
  direction: 'min',
  accessor: (point) => point.latency_ms,
};

/**
 * The metrics a user may plot on either axis: cost and latency (always present, minimized), plus one
 * option per evaluator seen across the group's points (maximized). Evaluator names are dynamic — they
 * differ per customer — so they're derived from the data rather than hardcoded.
 */
export function deriveParetoMetrics(points: readonly ParetoMetricPoint[]): ParetoMetric[] {
  const evaluatorNames = [
    ...new Set(points.flatMap((point) => Object.keys(point.evaluators ?? {}))),
  ].sort();
  const evaluatorMetrics = evaluatorNames.map<ParetoMetric>((name) => ({
    id: `evaluators.${name}`,
    label: metricLabel(`evaluators.${name}`),
    direction: 'max',
    accessor: (point) => point.evaluators?.[name],
  }));
  return [COST_METRIC, LATENCY_METRIC, ...evaluatorMetrics];
}

export interface ParetoPlotPoint {
  readonly name: string;
  readonly x: number;
  readonly y: number;
  /** True when no other evaluation dominates this one on both axes. */
  readonly onFrontier: boolean;
}

interface Coords {
  readonly x: number;
  readonly y: number;
}

/** Whether `b` dominates `a`: at least as good on both axes and strictly better on at least one. */
function dominates(a: Coords, b: Coords, xDir: MetricDirection, yDir: MetricDirection): boolean {
  const atLeastAsGood = (av: number, bv: number, dir: MetricDirection): boolean =>
    dir === 'min' ? bv <= av : bv >= av;
  const strictlyBetter = (av: number, bv: number, dir: MetricDirection): boolean =>
    dir === 'min' ? bv < av : bv > av;
  return (
    atLeastAsGood(a.x, b.x, xDir) &&
    atLeastAsGood(a.y, b.y, yDir) &&
    (strictlyBetter(a.x, b.x, xDir) || strictlyBetter(a.y, b.y, yDir))
  );
}

/**
 * Build plot points for two metrics and flag which lie on the Pareto frontier — the evaluations not
 * dominated by any other on both axes. Points missing either metric (non-finite) are dropped.
 */
export function buildParetoPoints(
  points: readonly ParetoMetricPoint[],
  xMetric: ParetoMetric,
  yMetric: ParetoMetric
): ParetoPlotPoint[] {
  const coords = points
    .map((point): { name: string; x: number; y: number } | null => {
      const x = xMetric.accessor(point);
      const y = yMetric.accessor(point);
      if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) return null;
      return { name: point.name, x, y };
    })
    .filter((point): point is { name: string; x: number; y: number } => point !== null);

  return coords.map((point) => ({
    ...point,
    onFrontier: !coords.some(
      (other) => other !== point && dominates(point, other, xMetric.direction, yMetric.direction)
    ),
  }));
}
