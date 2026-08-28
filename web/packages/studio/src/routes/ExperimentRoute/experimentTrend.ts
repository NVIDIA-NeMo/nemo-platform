// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import type { EvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import type { MetricTrendSeries } from '@studio/components/charts/MetricTrendPanel';
import { evaluatorLabel } from '@studio/routes/agents/AgentDetailRoute/evaluations/formatRollups';

/**
 * How many of an experiment's evaluations feed its trendline. Bounds the per-card request on a
 * list page that renders several of them; older evaluations fall off the left of the chart.
 */
export const TREND_EVALUATION_LIMIT = 100;

/** Window the delta is measured over. Fixed rather than "previous run" so the number means the
 *  same thing on an experiment that runs hourly and one that runs monthly. */
export const DELTA_WINDOW_DAYS = 7;
export const DELTA_COMPARISON_LABEL = `vs. ${DELTA_WINDOW_DAYS} days ago`;

const DELTA_WINDOW_MS = DELTA_WINDOW_DAYS * 24 * 60 * 60 * 1000;

/**
 * The delta is already a relative change (a ratio of two same-unit scores), so the percent sign is
 * accurate whatever the underlying scale. One decimal keeps it to the width the tag has room for.
 */
export const formatTrendDelta = (delta: number): string =>
  `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toFixed(1)}%`;

/** A score with the timestamp it was published at, which the delta needs and `MetricTrendPoint` drops. */
interface StampedScore {
  at: number;
  value: number;
}

const pointLabel = (at: number): string =>
  new Date(at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

/**
 * Change over the last {@link DELTA_WINDOW_DAYS}, as a percentage of the baseline: latest against
 * the newest score that is at least a full window older.
 *
 * Relative rather than a raw difference because evaluator scores carry no scale metadata (see
 * `formatEvaluatorScore`), so a raw difference is unreadable at the scale scores land on. A ratio
 * of two same-unit numbers is scale-free, so it stays meaningful whichever the score is.
 *
 * Undefined when nothing is old enough to compare against, or when the baseline is zero — there is
 * no percentage change from nothing. Divided by the absolute baseline so a negative baseline still
 * yields "moved up" for an increase.
 */
const deltaOverWindow = (scores: StampedScore[]): number | undefined => {
  const latest = scores.at(-1);
  if (!latest) return undefined;
  const cutoff = latest.at - DELTA_WINDOW_MS;
  const baseline = scores.filter((score) => score.at <= cutoff).at(-1);
  if (!baseline || baseline.value === 0) return undefined;
  return ((latest.value - baseline.value) / Math.abs(baseline.value)) * 100;
};

/**
 * Roll an experiment's evaluations up into one trendline per evaluator, alphabetized by label.
 *
 * An evaluation with no `created_at` is dropped: a trend line needs a position on the x-axis, and
 * a point with no timestamp cannot be placed or compared against the delta window.
 */
export const toTrendSeries = (evaluations: EvaluationResponse[]): MetricTrendSeries[] => {
  const byEvaluator = new Map<string, StampedScore[]>();

  for (const evaluation of evaluations) {
    const at = Date.parse(evaluation.created_at ?? '');
    if (!Number.isFinite(at)) continue;

    for (const [evaluator, aggregate] of Object.entries(evaluation.aggregate_scores ?? {})) {
      const mean = aggregate?.mean;
      if (typeof mean !== 'number' || !Number.isFinite(mean)) continue;
      byEvaluator.set(evaluator, [...(byEvaluator.get(evaluator) ?? []), { at, value: mean }]);
    }
  }

  return [...byEvaluator.entries()]
    .map(([evaluator, values]) => {
      const scores = [...values].sort((a, b) => a.at - b.at);
      return {
        id: evaluator,
        label: snakeCaseToTitleCase(evaluatorLabel(evaluator)),
        value: scores.at(-1)?.value ?? 0,
        delta: deltaOverWindow(scores),
        points: scores.map((score) => ({ label: pointLabel(score.at), value: score.value })),
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
};
