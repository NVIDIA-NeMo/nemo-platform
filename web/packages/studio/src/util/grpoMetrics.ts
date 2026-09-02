// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatNumericValue } from '@nemo/common/src/components/charts/format';
import type { ChartReferenceLine } from '@nemo/common/src/components/charts/types';
import type { StatTileStatus } from '@nemo/common/src/components/StatTile';
import { formatTimeInSeconds } from '@nemo/common/src/utils/date';
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
  truncationRate: 'train_truncation_rate',
  tokenMultProbError: 'train_token_mult_prob_error',
  genKlError: 'train_gen_kl_error',
  samplingImportanceRatio: 'train_sampling_importance_ratio',
  approxEntropy: 'train_approx_entropy',
  genTokens: 'train_gen_tokens_per_sample/mean',
  /**
   * Wall clock for one step. NeMo-RL logs it under a `timing/train` prefix that the logger
   * re-spells as `timing/` before the `train_` phase prefix goes on, hence the nested name.
   */
  stepTime: 'train_timing/total_step_time',
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

/**
 * The median rather than the latest or the mean: step time is spiky — a checkpoint save or one
 * straggler rollout doubles a single step — and an outlier moves a mean but not a median.
 */
export const medianValue = (series: CustomizationMetricValue[] | undefined): number | undefined => {
  if (!series?.length) return undefined;
  const sorted = series.map((point) => point.value).sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
};

/**
 * A step takes seconds to minutes. Under a minute the decimal is what separates a 34s step from
 * a 35s one; past it, `1m 15s` reads better than `75.0s`.
 */
export const formatStepDuration = (value: number): string =>
  value < 60 ? `${value.toFixed(1)}s` : formatTimeInSeconds(value);

/** Parallel arrays over one shared step axis. */
export interface RewardChartData {
  steps: number[];
  training: (number | null)[];
  validation: (number | null)[];
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

  const steps = [...new Set([...trainingByStep.keys(), ...validationByStep.keys()])].sort(
    (a, b) => a - b
  );

  return {
    steps,
    training: steps.map((step) => trainingByStep.get(step) ?? null),
    validation: steps.map((step) => validationByStep.get(step) ?? null),
  };
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
 * `sampling_importance_ratio` is the sequence-level twin of that drift — the mean ratio between
 * the training policy and the one that generated the rollouts, so 1 exactly when they agree.
 * Averaging over whole sequences rather than tokens makes it the noisier of the two, hence its
 * own wider band rather than a share of `LOGPROB_DRIFT_*`.
 */
const IMPORTANCE_RATIO_WATCH = 0.05;
const IMPORTANCE_RATIO_ALERT = 0.1;

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
 * A subset of what the backend keeps a history for. `policy_kl_error`, `js_divergence_error` and
 * `kl_penalty` all store curves too; each is another reading of the off-policy drift the three
 * drift entries below already cover, so a fifth and sixth tile would only pad the grid.
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
    id: 'samplingImportanceRatio',
    metric: GRPO_METRIC.samplingImportanceRatio,
    title: 'Sampling importance ratio',
    hint: 'should hover near 1',
    // Read against 1 rather than as a deviation from it: three decimals put the interesting digits
    // on the tile, and "1.002" says which side of the target the run sits on where "0.2%" cannot.
    formatValue: (value) => value.toFixed(3),
    evaluate: (series) => {
      const drift = Math.abs(latest(series) - 1);
      if (drift > IMPORTANCE_RATIO_ALERT) return { status: 'error', label: 'diverged' };
      if (drift > IMPORTANCE_RATIO_WATCH) return { status: 'warning', label: 'drifting' };
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
    title: 'Mean generated tokens per response',
    hint: 'response length',
    formatValue: formatNumericValue,
    chart: true,
  },
  {
    id: 'stepTime',
    metric: GRPO_METRIC.stepTime,
    title: 'Training step time',
    hint: 'wall clock per step',
    formatValue: formatStepDuration,
    // The axis is read for pace, not precision, so it drops to whole units — and `34.0s` next to
    // `34.5s` invites reading a tick gap as real when it is the rounding.
    formatAxisValue: (value) => formatTimeInSeconds(value) || formatStepDuration(value),
    // No tile here: the run's pace is summarised beside the reward chart, as a median over the
    // whole run rather than whichever step happened to report last.
    chart: true,
  },
];
