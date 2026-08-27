// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import type { MetricTrendSeries } from '@studio/components/charts/MetricTrendPanel';
import { evaluatorLabel } from '@studio/routes/agents/AgentDetailRoute/evaluations/formatRollups';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

/** Enough to show what the agent is being measured against without turning the overview into the
 *  Evaluations tab. The rest stay one click away under Evaluations → Experiments. Applied to each
 *  group separately, so pinning favorites never pushes the recent ones off the page. */
export const RECENT_EXPERIMENT_LIMIT = 3;

/** Window the delta is measured over. Fixed rather than "previous run" so the number means the same
 *  thing on an experiment that runs hourly and one that runs monthly. */
export const DELTA_WINDOW_DAYS = 7;
export const DELTA_COMPARISON_LABEL = `vs. ${DELTA_WINDOW_DAYS} days ago`;

const DELTA_WINDOW_MS = DELTA_WINDOW_DAYS * 24 * 60 * 60 * 1000;

export interface RecentExperiment {
  id: string;
  /** Null when the experiment fell outside the fetched page and could not be resolved. Such a card
   *  keeps its scores but loses its label and its link. */
  name: string | null;
  description: string | null;
  latestCreatedAt: string | null;
  evaluationCount: number;
  /** One per evaluator seen anywhere in the experiment, alphabetized by label. */
  series: MetricTrendSeries[];
  isFavorite: boolean;
}

/** The overview's two groups: the experiments the user pinned, and everything else by recency. */
export interface GroupedRecentExperiments {
  favorites: RecentExperiment[];
  recent: RecentExperiment[];
}

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
 * `formatEvaluatorScore`). A raw difference is unreadable at the scale scores actually land on —
 * a solve rate moving .149 → .160 reads as "+0.011" — and it cannot be a percentage *point* either,
 * since that would assume the score is a 0–1 ratio when it may be a point count or a latency. A
 * ratio of two same-unit numbers is scale-free, so it stays meaningful whichever the score is.
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

const toSeries = (evaluator: string, scores: StampedScore[]): MetricTrendSeries => ({
  id: evaluator,
  label: snakeCaseToTitleCase(evaluatorLabel(evaluator)),
  value: scores.at(-1)?.value ?? 0,
  delta: deltaOverWindow(scores),
  points: scores.map((score) => ({ label: pointLabel(score.at), value: score.value })),
});

/**
 * Roll the agent's evaluations up into trend cards, split into favorites and everything else, each
 * group newest first.
 *
 * An evaluation feeds every experiment it belongs to, not just its first: membership is
 * many-to-many, so keying on `experiment_ids[0]` would drop a shared evaluation's scores and
 * timestamps from all but one of its experiments.
 *
 * Only experiments with `show_evaluations_over_time` set take part: a trend line over an
 * experiment's evaluations is only meaningful when those evaluations are successive runs of the
 * same measurement, which is exactly what that flag asserts. Experiments without it are left to the
 * Experiments tab, which compares their evaluations side by side instead.
 *
 * Derived from the evaluations rather than queried, for the same reason as `groupByExperiment`: the
 * experiments endpoint has no `agent_name` filter, so "which experiments cover this agent" is only
 * answerable through the evaluations that name it.
 *
 * An evaluation with no `created_at` is dropped from the series — a trend line needs a position on
 * the x-axis, and a point with no timestamp cannot be placed or compared. It still counts toward
 * `evaluationCount` so the card does not under-report how much has run.
 */
export const toRecentExperiments = (
  evaluations: AgentEvaluationRow[],
  limit: number = RECENT_EXPERIMENT_LIMIT
): GroupedRecentExperiments => {
  const byExperiment = new Map<
    string,
    { row: RecentExperiment; scores: Map<string, StampedScore[]> }
  >();

  for (const evaluation of evaluations) {
    for (const experiment of evaluation.experiments) {
      if (!experiment.showsEvaluationsOverTime) continue;

      const entry = byExperiment.get(experiment.id) ?? {
        row: {
          id: experiment.id,
          name: experiment.name,
          description: experiment.description,
          latestCreatedAt: null,
          evaluationCount: 0,
          series: [],
          isFavorite: experiment.isFavorite,
        },
        scores: new Map<string, StampedScore[]>(),
      };

      entry.row.name ??= experiment.name;
      entry.row.description ??= experiment.description;
      entry.row.evaluationCount += 1;
      if (
        evaluation.created_at &&
        (!entry.row.latestCreatedAt || evaluation.created_at > entry.row.latestCreatedAt)
      ) {
        entry.row.latestCreatedAt = evaluation.created_at;
      }

      const at = Date.parse(evaluation.created_at ?? '');
      if (Number.isFinite(at)) {
        for (const [evaluator, aggregate] of Object.entries(evaluation.aggregate_scores ?? {})) {
          const mean = aggregate?.mean;
          if (typeof mean !== 'number' || !Number.isFinite(mean)) continue;
          const existing = entry.scores.get(evaluator) ?? [];
          existing.push({ at, value: mean });
          entry.scores.set(evaluator, existing);
        }
      }

      byExperiment.set(experiment.id, entry);
    }
  }

  const rows = [...byExperiment.values()]
    .map(({ row, scores }) => ({
      ...row,
      series: [...scores.entries()]
        .map(([evaluator, values]) =>
          toSeries(
            evaluator,
            [...values].sort((a, b) => a.at - b.at)
          )
        )
        .sort((a, b) => a.label.localeCompare(b.label)),
    }))
    .sort((a, b) => (b.latestCreatedAt ?? '').localeCompare(a.latestCreatedAt ?? ''));

  return {
    favorites: rows.filter((row) => row.isFavorite).slice(0, limit),
    recent: rows.filter((row) => !row.isFavorite).slice(0, limit),
  };
};
