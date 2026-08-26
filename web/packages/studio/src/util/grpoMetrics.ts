// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatNumericValue } from '@nemo/common/src/components/charts/format';
import type { ChartReferenceLine } from '@nemo/common/src/components/charts/types';
import type { StatTileStatus } from '@nemo/common/src/components/StatTile';
import type {
  CustomizationMetricValue,
  CustomizationStatusDetailsWithMetrics,
} from '@studio/types/customization';

/**
 * Mirrors `GRPO_TIME_SERIES_METRICS` in `services/rl/.../nemo_rl/nemo_rl_logger.py`, the
 * allow-list deciding which metrics keep a history. A rename there needs one counterpart here.
 */
export const GRPO_METRIC = {
  trainReward: 'train_reward',
  /** GRPO's validation reward: `validate()` reports no loss, so this whole-pass mean is the curve. */
  validationReward: 'val_accuracy',
  /** Not in the backend allow-list today, so it has no history and the reward band stays off. */
  rewardSpread: 'train_total_reward/stddev',
  truncationRate: 'train_truncation_rate',
  tokenMultProbError: 'train_token_mult_prob_error',
  genKlError: 'train_gen_kl_error',
  approxEntropy: 'train_approx_entropy',
  genTokens: 'train_gen_tokens_per_sample/mean',
} as const;

const isMetricPoint = (point: unknown): point is CustomizationMetricValue =>
  typeof point === 'object' &&
  point !== null &&
  Number.isFinite((point as { step?: unknown }).step) &&
  Number.isFinite((point as { value?: unknown }).value);

/**
 * `status_details` is an untyped blob, so points are validated rather than cast. A malformed
 * point costs itself, not the curve — the server's seeded blob may be half-written.
 */
export const readSeries = (
  statusDetails: CustomizationStatusDetailsWithMetrics | undefined,
  name: string
): CustomizationMetricValue[] | undefined => {
  const raw: unknown = statusDetails?.metrics?.[name];
  if (!Array.isArray(raw)) return undefined;
  const points = raw.filter(isMetricPoint).sort((a, b) => a.step - b.step);
  return points.length > 0 ? points : undefined;
};

/** Parallel arrays over one shared step axis, in the shape `RangeBandSeries` wants. */
export interface RewardChartData {
  steps: number[];
  training: (number | null)[];
  /** `mean - σ` where a spread series exists at that step, else `null`. */
  trainingLower: (number | null)[];
  trainingUpper: (number | null)[];
  validation: (number | null)[];
  /** Whether any band bound is plottable — false renders two plain lines. */
  hasSpread: boolean;
}

const byStep = (series: CustomizationMetricValue[] | undefined): Map<number, number> =>
  new Map((series ?? []).map((point) => [point.step, point.value]));

/**
 * Merges the reward curves onto one sorted step axis. Validation runs every N steps, so its array
 * is mostly `null` — the chart bridges those gaps rather than this inventing values.
 */
export const buildRewardChartData = (
  statusDetails: CustomizationStatusDetailsWithMetrics | undefined
): RewardChartData | undefined => {
  const training = readSeries(statusDetails, GRPO_METRIC.trainReward);
  const validation = readSeries(statusDetails, GRPO_METRIC.validationReward);
  if (!training && !validation) return undefined;

  const trainingByStep = byStep(training);
  const validationByStep = byStep(validation);
  const spreadByStep = byStep(readSeries(statusDetails, GRPO_METRIC.rewardSpread));

  const steps = [...new Set([...trainingByStep.keys(), ...validationByStep.keys()])].sort(
    (a, b) => a - b
  );

  const data: RewardChartData = {
    steps,
    training: [],
    trainingLower: [],
    trainingUpper: [],
    validation: [],
    hasSpread: false,
  };

  for (const step of steps) {
    const mean = trainingByStep.get(step);
    const spread = spreadByStep.get(step);
    const banded = mean !== undefined && spread !== undefined;

    data.training.push(mean ?? null);
    data.trainingLower.push(banded ? mean - spread : null);
    data.trainingUpper.push(banded ? mean + spread : null);
    data.validation.push(validationByStep.get(step) ?? null);
    data.hasSpread ||= banded;
  }

  return data;
};

export interface DiagnosticVerdict {
  status: StatTileStatus;
  /** One word beside the value: `ok`, `falling`, `high`. */
  label: string;
}

export interface GrpoDiagnostic {
  id: string;
  /** Series name; also the tile label, since operators grep NeMo-RL logs for these. */
  metric: string;
  /** Chart heading. Only rendered for a `chart` entry; a tile is labelled `metric`. */
  title: string;
  hint: string;
  formatValue: (value: number) => string;
  /**
   * For a metric that barely moves, recharts' ticks fall closer together than the tile's rounding
   * — a drift series spanning 1.001 to 1.004 renders "0.2%" twice, which reads as a bug.
   */
  formatAxisValue?: (value: number) => string;
  /** Reads the whole series, since entropy is judged on its trend rather than its latest value. */
  evaluate?: (series: CustomizationMetricValue[]) => DiagnosticVerdict;
  referenceLines?: ChartReferenceLine[];
  tile?: boolean;
  /** Charted only when the metric's *shape* carries the diagnosis; the rest are read off a tile. */
  chart?: boolean;
}

const OK: DiagnosticVerdict = { status: 'success', label: 'ok' };

/** Above this, generation and training have drifted far enough apart to distrust the gradients. */
const GEN_KL_THRESHOLD = 1e-3;
/** Spelled out rather than derived: `toExponential(1)` renders it as the clumsier "1.0e-3". */
const GEN_KL_THRESHOLD_LABEL = '1e-3';

/**
 * `token_mult_prob_error` is a ratio centred on 1, not a percentage, so the threshold is on
 * `|v - 1|` — rendering the raw value would show a healthy 1.004 run as 100%.
 */
const LOGPROB_DRIFT_WATCH = 0.01;
const LOGPROB_DRIFT_ALERT = 0.02;

/**
 * Judged on the decline from the start rather than an absolute floor: healthy entropy depends on
 * the model and task, and collapse looks fine on the reward curve until generations degenerate.
 */
const ENTROPY_COLLAPSE_DROP = 0.5;

const latest = (series: CustomizationMetricValue[]): number => series[series.length - 1].value;

/** Explicit y bounds, or `undefined` where the data's own range is fine. */
export interface ThresholdAxisBounds {
  yAxisMin?: number;
  yAxisMax?: number;
}

/** Fraction of the plotted range left above a threshold so its label is not clipped. */
const THRESHOLD_HEADROOM = 0.1;

/**
 * Recharts fits the axis to the data and drops any reference line outside it, so a threshold
 * vanishes exactly while the series is comfortably under it. Widen the axis to keep it visible.
 */
export const thresholdAxisBounds = (
  diagnostic: GrpoDiagnostic,
  series: CustomizationMetricValue[]
): ThresholdAxisBounds => {
  const thresholds = diagnostic.referenceLines?.map((line) => line.y) ?? [];
  if (thresholds.length === 0 || series.length === 0) return {};

  const values = series.map((point) => point.value);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const min = Math.min(dataMin, ...thresholds);
  const max = Math.max(dataMax, ...thresholds);
  const headroom = (max - min) * THRESHOLD_HEADROOM;

  // Only override the bound a threshold actually pushes past; the other keeps fitting the data.
  return {
    yAxisMin: min < dataMin ? min - headroom : undefined,
    yAxisMax: max > dataMax ? max + headroom : undefined,
  };
};

const formatExponential = (value: number): string => value.toExponential(1);

/**
 * Nothing emits `policy_kl_error`, `js_divergence_error` or `sampling_importance_ratio`, and
 * `train_step_time` arrives under a `timing/` prefix the RL logger deliberately routes nowhere.
 */
export const GRPO_DIAGNOSTICS: GrpoDiagnostic[] = [
  {
    id: 'genKlError',
    metric: GRPO_METRIC.genKlError,
    title: 'Generation KL',
    hint: `flag above ${GEN_KL_THRESHOLD_LABEL}`,
    formatValue: formatExponential,
    evaluate: (series) =>
      latest(series) > GEN_KL_THRESHOLD ? { status: 'warning', label: 'high' } : OK,
    referenceLines: [
      {
        y: GEN_KL_THRESHOLD,
        label: `threshold ${GEN_KL_THRESHOLD_LABEL}`,
        // Warning-tinted so it reads as a limit rather than another gridline.
        color: 'var(--text-color-feedback-warning)',
      },
    ],
    tile: true,
    chart: true,
  },
  {
    id: 'tokenMultProbError',
    metric: GRPO_METRIC.tokenMultProbError,
    title: 'Rollout / training logprob drift',
    hint: `flag above ${LOGPROB_DRIFT_WATCH * 100}-${LOGPROB_DRIFT_ALERT * 100}%`,
    formatValue: (value) => `${(Math.abs(value - 1) * 100).toFixed(1)}%`,
    evaluate: (series) => {
      const drift = Math.abs(latest(series) - 1);
      if (drift > LOGPROB_DRIFT_ALERT) return { status: 'error', label: 'high' };
      if (drift > LOGPROB_DRIFT_WATCH) return { status: 'warning', label: 'elevated' };
      return OK;
    },
    tile: true,
  },
  {
    id: 'approxEntropy',
    metric: GRPO_METRIC.approxEntropy,
    title: 'Policy entropy',
    hint: 'entropy collapse risk',
    formatValue: (value) => value.toFixed(2),
    evaluate: (series) => {
      const start = series[0].value;
      if (start === 0) return OK;
      const drop = (start - latest(series)) / Math.abs(start);
      return drop > ENTROPY_COLLAPSE_DROP ? { status: 'warning', label: 'falling' } : OK;
    },
    tile: true,
    chart: true,
  },
  {
    id: 'genTokens',
    metric: GRPO_METRIC.genTokens,
    // Per rollout, not per step: the per-step total is this times a constant, so same shape.
    title: 'Generated tokens per rollout',
    hint: 'response length',
    formatValue: formatNumericValue,
    chart: true,
  },
];
