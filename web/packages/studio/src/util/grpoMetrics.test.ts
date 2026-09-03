// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationStatusDetailsWithMetrics } from '@studio/types/customization';
import {
  buildRewardChartData,
  GRPO_DIAGNOSTICS,
  GRPO_METRIC,
  medianValue,
  readSeries,
  thresholdAxisBounds,
} from '@studio/util/grpoMetrics';

const details = (metrics: Record<string, unknown>): CustomizationStatusDetailsWithMetrics =>
  ({ metrics }) as unknown as CustomizationStatusDetailsWithMetrics;

const diagnostic = (id: string) => {
  const found = GRPO_DIAGNOSTICS.find((entry) => entry.id === id);
  if (!found) throw new Error(`No diagnostic named ${id}`);
  return found;
};

describe('readSeries', () => {
  it('returns undefined when the run reported no such series', () => {
    expect(readSeries(undefined, GRPO_METRIC.trainReward)).toBeUndefined();
    expect(readSeries(details({}), GRPO_METRIC.trainReward)).toBeUndefined();
    expect(readSeries(details({ train_reward: [] }), GRPO_METRIC.trainReward)).toBeUndefined();
  });

  it('reads a name containing a slash', () => {
    const series = readSeries(
      details({ 'train_gen_tokens_per_sample/mean': [{ step: 1, value: 689.3 }] }),
      GRPO_METRIC.genTokens
    );
    expect(series).toEqual([{ step: 1, value: 689.3 }]);
  });

  it('drops malformed points rather than the whole curve', () => {
    const series = readSeries(
      details({
        train_reward: [
          { step: 1, value: 0.2 },
          null,
          { step: 2 },
          { step: 3, value: Number.NaN },
          'nonsense',
          { step: 4, value: 0.5 },
        ],
      }),
      GRPO_METRIC.trainReward
    );
    expect(series).toEqual([
      { step: 1, value: 0.2 },
      { step: 4, value: 0.5 },
    ]);
  });

  it('sorts by step, since a restarted process appends to a seeded curve', () => {
    const series = readSeries(
      details({
        train_reward: [
          { step: 10, value: 0.5 },
          { step: 2, value: 0.2 },
        ],
      }),
      GRPO_METRIC.trainReward
    );
    expect(series?.map((point) => point.step)).toEqual([2, 10]);
  });

  it('ignores a metrics value that is not an array', () => {
    expect(readSeries(details({ train_reward: 0.617 }), GRPO_METRIC.trainReward)).toBeUndefined();
  });
});

describe('buildRewardChartData', () => {
  it('returns undefined when neither reward curve was reported', () => {
    expect(buildRewardChartData(undefined)).toBeUndefined();
    expect(buildRewardChartData(details({ train_loss: [{ step: 1, value: 2 }] }))).toBeUndefined();
  });

  it('leaves gaps where a sparse validation pass did not run', () => {
    const data = buildRewardChartData(
      details({
        train_reward: [
          { step: 1, value: 0.2 },
          { step: 2, value: 0.3 },
          { step: 3, value: 0.4 },
        ],
        val_accuracy: [{ step: 3, value: 0.35 }],
      })
    );

    expect(data?.steps).toEqual([1, 2, 3]);
    expect(data?.training).toEqual([0.2, 0.3, 0.4]);
    expect(data?.validation).toEqual([null, null, 0.35]);
  });

  it('keeps a validation step the training curve never reported', () => {
    const data = buildRewardChartData(
      details({
        train_reward: [{ step: 2, value: 0.3 }],
        val_accuracy: [{ step: 5, value: 0.35 }],
      })
    );

    expect(data?.steps).toEqual([2, 5]);
    expect(data?.training).toEqual([0.3, null]);
    expect(data?.validation).toEqual([null, 0.35]);
  });
});

describe('GRPO diagnostics', () => {
  it('reads token_mult_prob_error as a deviation from 1, not as a raw percentage', () => {
    // NeMo-RL reports this as a ratio centred on 1 — the golden backend fixture logs 1.011.
    // Rendering it raw would show a healthy run as ~101%.
    const { formatValue, evaluate } = diagnostic('tokenMultProbError');

    expect(formatValue(1.004)).toBe('0.4%');
    expect(formatValue(1.011)).toBe('1.1%');
    expect(formatValue(0.994)).toBe('0.6%');

    expect(evaluate?.([{ step: 1, value: 1.004 }])).toEqual({ status: 'success', label: 'ok' });
    expect(evaluate?.([{ step: 1, value: 1.011 }])).toEqual({
      status: 'warning',
      label: 'elevated',
    });
    expect(evaluate?.([{ step: 1, value: 1.05 }])).toEqual({ status: 'error', label: 'high' });
    // Drift below 1 is just as far off-policy as drift above it.
    expect(evaluate?.([{ step: 1, value: 0.95 }])).toEqual({ status: 'error', label: 'high' });
  });

  it('flags gen_kl_error above 1e-3', () => {
    const { formatValue, evaluate } = diagnostic('genKlError');

    expect(formatValue(0.00054)).toBe('5.4e-4');
    expect(evaluate?.([{ step: 1, value: 5.4e-4 }])).toEqual({ status: 'success', label: 'ok' });
    expect(evaluate?.([{ step: 1, value: 4.1e-3 }])).toEqual({ status: 'warning', label: 'high' });
  });

  it('judges entropy on its decline from the start, not on an absolute floor', () => {
    const { evaluate } = diagnostic('approxEntropy');

    // 0.98 -> 0.31 is a 68% drop: the classic collapse.
    expect(
      evaluate?.([
        { step: 1, value: 0.98 },
        { step: 500, value: 0.31 },
      ])
    ).toEqual({ status: 'warning', label: 'falling' });

    // A low but steady entropy is not a collapse.
    expect(
      evaluate?.([
        { step: 1, value: 0.32 },
        { step: 500, value: 0.31 },
      ])
    ).toEqual({ status: 'success', label: 'ok' });
  });

  it('reads sampling_importance_ratio against 1 rather than as a deviation from it', () => {
    const { formatValue, evaluate } = diagnostic('samplingImportanceRatio');

    expect(formatValue(1.002)).toBe('1.002');
    expect(formatValue(0.9994)).toBe('0.999');

    expect(evaluate?.([{ step: 1, value: 1.002 }])).toEqual({ status: 'success', label: 'ok' });
    expect(evaluate?.([{ step: 1, value: 1.07 }])).toEqual({
      status: 'warning',
      label: 'drifting',
    });
    expect(evaluate?.([{ step: 1, value: 1.2 }])).toEqual({ status: 'error', label: 'diverged' });
    // Sampling below the training policy is just as far off-policy as sampling above it.
    expect(evaluate?.([{ step: 1, value: 0.8 }])).toEqual({ status: 'error', label: 'diverged' });
  });

  it('renders step time in seconds on the tile and whole units on the axis', () => {
    const { formatValue, formatAxisValue } = diagnostic('stepTime');

    expect(formatValue(34.2)).toBe('34.2s');
    expect(formatValue(75)).toBe('1m 15s');
    // The axis rounds, so two neighbouring ticks cannot render as the same string with a decimal.
    expect(formatAxisValue?.(34.6)).toBe('34s');
    expect(formatAxisValue?.(300)).toBe('5m');
    // `formatTimeInSeconds` renders sub-second values as an empty string; the tile format covers it.
    expect(formatAxisValue?.(0.4)).toBe('0.4s');
  });

  it('names only metrics the backend actually stores a history for', () => {
    // Mirrors GRPO_TIME_SERIES_METRICS in nemo_rl_logger.py. The names left out store a history
    // too — they are further readings of the drift the first two entries already report.
    expect(GRPO_DIAGNOSTICS.map((entry) => entry.metric)).toEqual([
      'train_gen_kl_error',
      'train_token_mult_prob_error',
      'train_sampling_importance_ratio',
      'train_approx_entropy',
      'train_gen_tokens_per_sample/mean',
      'train_timing/total_step_time',
    ]);
  });

  it('widens the axis so a threshold the run sits under stays on the chart', () => {
    // Recharts fits the domain to the data and discards anything outside it, so gen_kl_error's
    // 1e-3 line renders nothing at all on a healthy run peaking at 5.4e-4.
    const genKl = diagnostic('genKlError');
    const bounds = thresholdAxisBounds(genKl, [
      { step: 1, value: 1.2e-4 },
      { step: 500, value: 5.4e-4 },
    ]);

    expect(bounds.yAxisMax).toBeGreaterThan(1e-3);
    // The data never goes below its own floor, so that bound keeps fitting the data.
    expect(bounds.yAxisMin).toBeUndefined();
  });

  it('leaves the axis alone when the data already covers the threshold', () => {
    const bounds = thresholdAxisBounds(diagnostic('genKlError'), [
      { step: 1, value: 1e-4 },
      { step: 500, value: 4.1e-3 },
    ]);

    expect(bounds).toEqual({ yAxisMin: undefined, yAxisMax: undefined });
  });

  it('has no opinion on the axis for a diagnostic with no threshold', () => {
    expect(thresholdAxisBounds(diagnostic('approxEntropy'), [{ step: 1, value: 0.5 }])).toEqual({});
    expect(thresholdAxisBounds(diagnostic('genKlError'), [])).toEqual({});
  });

  it('charts only the metrics whose shape carries the diagnosis', () => {
    // Drift and advantage centering are read as "where is it now", which their tile answers.
    expect(GRPO_DIAGNOSTICS.filter((entry) => entry.chart).map((entry) => entry.title)).toEqual([
      'Generation KL',
      'Policy entropy',
      'Mean generated tokens per response',
      'Training step time',
    ]);
    // Step time is the one charted metric with no tile here: its summary sits beside the reward
    // chart as a median over the run, which the latest step's value would misreport.
    expect(GRPO_DIAGNOSTICS.filter((entry) => entry.tile).map((entry) => entry.metric)).toEqual([
      'train_gen_kl_error',
      'train_token_mult_prob_error',
      'train_sampling_importance_ratio',
      'train_approx_entropy',
    ]);
  });
});

describe('medianValue', () => {
  it('has nothing to report for a series the run never wrote', () => {
    expect(medianValue(undefined)).toBeUndefined();
    expect(medianValue([])).toBeUndefined();
  });

  it('averages the middle pair on an even-length series', () => {
    expect(
      medianValue([
        { step: 1, value: 29.8 },
        { step: 2, value: 33.6 },
        { step: 3, value: 34.8 },
        { step: 4, value: 35.4 },
      ])
    ).toBe(34.2);
  });

  it('takes the middle value on an odd-length series', () => {
    expect(
      medianValue([
        { step: 1, value: 30 },
        { step: 2, value: 34 },
        { step: 3, value: 36 },
      ])
    ).toBe(34);
  });

  it('ignores a spike that would drag a mean, which is the point of using it', () => {
    // A checkpoint save or one straggler rollout doubles a single step's wall clock.
    const series = [
      { step: 1, value: 33 },
      { step: 2, value: 34 },
      { step: 3, value: 35 },
      { step: 4, value: 36 },
      { step: 5, value: 400 },
    ];

    expect(medianValue(series)).toBe(35);
  });

  it('sorts by value, not by the step order readSeries left it in', () => {
    expect(
      medianValue([
        { step: 1, value: 100 },
        { step: 2, value: 1 },
        { step: 3, value: 10 },
      ])
    ).toBe(10);
  });
});
