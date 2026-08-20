// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FinetuningType } from '@nemo/sdk/generated/platform/schema';
import type {
  CustomizationJob,
  CustomizationJobStatusDetails,
} from '@studio/util/customizationBackend';
import {
  formatFinetuningType,
  formatTrainingPhase,
  getBaseModel,
  getCustomizationTrainingProgress,
  getCustomizationTrainingSteps,
  getDatasetUri,
  getFailureMessage,
  getFinetuningType,
  getFormattedCustomizationStatus,
  getJobDuration,
  getJobStartDate,
  getFormattedTrainingType,
  getProgressLogs,
  formatMetricValue,
  formatStepCount,
  getLossTiles,
  getTrainingProgressTiles,
  getTrainingBatchSize,
  getTrainingDiagnosticsTiles,
  getTrainingTelemetry,
} from '@studio/util/customizations';

/** Minimal automodel job (carries `parallelism`). */
const automodelJob = (spec: Record<string, unknown>): CustomizationJob =>
  ({ spec: { parallelism: {}, ...spec } }) as unknown as CustomizationJob;

/** Minimal unsloth job (carries `hardware`). */
const unslothJob = (spec: Record<string, unknown>): CustomizationJob =>
  ({ spec: { hardware: {}, ...spec } }) as unknown as CustomizationJob;

describe('getFormattedTrainingType', () => {
  it('Returns the correctly formatted training type', () => {
    expect(getFormattedTrainingType('lora')).toEqual('LoRA');
    expect(getFormattedTrainingType('sft')).toEqual('SFT');
    expect(getFormattedTrainingType('distillation')).toEqual('Distillation');
    expect(getFormattedTrainingType('all_weights')).toEqual('All Weights');
  });
});

describe('formatFinetuningType', () => {
  it.each([
    ['lora', 'LoRA'],
    ['lora_merged', 'LoRA Merged'],
    ['all_weights', 'All Weights'],
    ['dora', 'DoRA'],
  ])('formats %s as %s', (input, expected) => {
    expect(formatFinetuningType(input as FinetuningType)).toEqual(expected);
  });
});

describe('getFormattedCustomizationStatus', () => {
  it('Returns the correctly formatted status', () => {
    expect(getFormattedCustomizationStatus(undefined)).toEqual('');
    expect(getFormattedCustomizationStatus('created')).toEqual('Created');
    expect(getFormattedCustomizationStatus('completed')).toEqual('Completed');
    expect(getFormattedCustomizationStatus('running')).toEqual('Running');
  });

  it('appends progress percentage when provided', () => {
    expect(getFormattedCustomizationStatus('running', 45.7)).toEqual('Running (45%)');
  });
});

describe('getBaseModel', () => {
  it('returns empty string when job is undefined', () => {
    expect(getBaseModel(undefined)).toBe('');
  });

  it('returns model string for automodel jobs', () => {
    expect(getBaseModel(automodelJob({ model: 'my-model' }))).toBe('my-model');
  });

  it('returns model.name for unsloth jobs', () => {
    expect(getBaseModel(unslothJob({ model: { name: 'my-model' } }))).toBe('my-model');
  });

  it('returns empty string when the model is missing', () => {
    expect(getBaseModel(automodelJob({}))).toBe('');
  });
});

describe('getDatasetUri', () => {
  it('returns dataset.training for automodel jobs', () => {
    expect(getDatasetUri(automodelJob({ dataset: { training: 'urn:dataset:abc' } }))).toBe(
      'urn:dataset:abc'
    );
  });

  it('returns dataset.path for unsloth jobs', () => {
    expect(getDatasetUri(unslothJob({ dataset: { path: 'urn:dataset:xyz' } }))).toBe(
      'urn:dataset:xyz'
    );
  });

  it('returns empty string when job is undefined', () => {
    expect(getDatasetUri(undefined)).toBe('');
  });
});

describe('getTrainingBatchSize', () => {
  it('uses global_batch_size for automodel', () => {
    expect(getTrainingBatchSize(automodelJob({ batch: { global_batch_size: 16 } }))).toBe(16);
  });

  it('uses per_device_train_batch_size for unsloth', () => {
    expect(getTrainingBatchSize(unslothJob({ batch: { per_device_train_batch_size: 4 } }))).toBe(4);
  });
});

describe('getFailureMessage', () => {
  it('returns joined details when failure log exists', () => {
    const statusDetails = {
      status_logs: [
        { message: 'Failed to train', detail: 'OOM error' },
        { message: 'cleanup', detail: 'resources freed' },
      ],
    } as unknown as CustomizationJobStatusDetails;
    expect(getFailureMessage(statusDetails)).toBe('OOM error\nresources freed');
  });

  it('returns empty string when no failure logs', () => {
    const statusDetails = {
      status_logs: [{ message: 'Running', detail: 'step 1' }],
    } as unknown as CustomizationJobStatusDetails;
    expect(getFailureMessage(statusDetails)).toBe('');
  });

  it('returns empty string when status_logs is missing', () => {
    const statusDetails = {} as unknown as CustomizationJobStatusDetails;
    expect(getFailureMessage(statusDetails)).toBe('');
  });
});

describe('getProgressLogs', () => {
  it('returns status_logs array', () => {
    const logs = [{ message: 'step 1' }];
    const statusDetails = { status_logs: logs } as unknown as CustomizationJobStatusDetails;
    expect(getProgressLogs(statusDetails)).toEqual(logs);
  });

  it('returns empty array when status_logs is missing', () => {
    const statusDetails = {} as unknown as CustomizationJobStatusDetails;
    expect(getProgressLogs(statusDetails)).toEqual([]);
  });
});

describe('getCustomizationTrainingProgress', () => {
  it('returns empty string when no status_details', () => {
    const job = {} as unknown as CustomizationJob;
    expect(getCustomizationTrainingProgress(job)).toBe('');
  });

  it('returns empty string when epoch and percentage_done are both null', () => {
    const job = automodelJob({ schedule: { epochs: 5 } });
    (job as { status_details?: unknown }).status_details = {};
    expect(getCustomizationTrainingProgress(job)).toBe('');
  });

  it('returns formatted progress string', () => {
    const job = automodelJob({ schedule: { epochs: 5 } });
    (job as { status_details?: unknown }).status_details = { epoch: 2, percentage_done: 40 };
    expect(getCustomizationTrainingProgress(job)).toBe('2/5 (40%)');
  });

  it('handles missing epoch gracefully', () => {
    const job = automodelJob({ schedule: { epochs: 3 } });
    (job as { status_details?: unknown }).status_details = { percentage_done: 60 };
    expect(getCustomizationTrainingProgress(job)).toBe('0/3 (60%)');
  });
});

describe('getCustomizationTrainingSteps', () => {
  it('returns 0 when epochs is 0', () => {
    expect(getCustomizationTrainingSteps({ epochs: 0, trainingRecords: 100, batchSize: 10 })).toBe(
      0
    );
  });

  it('returns 0 when batchSize is 0', () => {
    expect(getCustomizationTrainingSteps({ epochs: 3, trainingRecords: 100, batchSize: 0 })).toBe(
      0
    );
  });

  it('returns 0 when trainingRecords is 0', () => {
    expect(getCustomizationTrainingSteps({ epochs: 3, trainingRecords: 0, batchSize: 10 })).toBe(0);
  });

  it('calculates steps with validation dataset', () => {
    // 3 * ceil(100/10) = 30
    expect(
      getCustomizationTrainingSteps({
        epochs: 3,
        trainingRecords: 100,
        batchSize: 10,
        hasValidationDataset: true,
      })
    ).toBe(30);
  });

  it('calculates steps without validation dataset (90% split)', () => {
    // 3 * ceil(ceil(100 * 0.9) / 10) = 3 * ceil(90/10) = 3 * 9 = 27
    expect(getCustomizationTrainingSteps({ epochs: 3, trainingRecords: 100, batchSize: 10 })).toBe(
      27
    );
  });

  it('handles non-even batch divisions', () => {
    // 2 * ceil(ceil(95 * 0.9) / 8) = 2 * ceil(86/8) = 2 * ceil(10.75) = 2 * 11 = 22
    expect(getCustomizationTrainingSteps({ epochs: 2, trainingRecords: 95, batchSize: 8 })).toBe(
      22
    );
  });
});

describe('getTrainingTelemetry', () => {
  const jobWithDetails = (details: Record<string, unknown>): CustomizationJob =>
    ({ status_details: details }) as unknown as CustomizationJob;

  it('returns an empty object when there is no status_details', () => {
    expect(getTrainingTelemetry(undefined)).toEqual({});
    expect(getTrainingTelemetry({} as CustomizationJob)).toEqual({});
  });

  it('coerces the live per-step telemetry keys', () => {
    expect(
      getTrainingTelemetry(
        jobWithDetails({
          phase: 'training',
          step: 4,
          max_steps: 10,
          num_epochs: 3,
          epoch: 1,
          train_loss: 0.42,
          val_loss: 0.55,
          train_lr: 0.000005,
          train_grad_norm: 1.25,
          checkpoint_path: 'ws/fileset/checkpoints/step-4',
        })
      )
    ).toEqual({
      phase: 'training',
      step: 4,
      maxSteps: 10,
      numEpochs: 3,
      epoch: 1,
      trainLoss: 0.42,
      valLoss: 0.55,
      learningRate: 0.000005,
      gradNorm: 1.25,
      checkpointPath: 'ws/fileset/checkpoints/step-4',
    });
  });

  it('reads the unqualified names jobs used before the phase prefix', () => {
    // Those jobs are already in the database and never change. Without the
    // fallback their Learning Rate and Gradient Norm render blank forever.
    expect(
      getTrainingTelemetry(
        jobWithDetails({
          train_loss: 0.42,
          lr: 0.000005,
          grad_norm: 1.25,
        })
      )
    ).toEqual({
      trainLoss: 0.42,
      learningRate: 0.000005,
      gradNorm: 1.25,
      phase: undefined,
      step: undefined,
      maxSteps: undefined,
      numEpochs: undefined,
      epoch: undefined,
      valLoss: undefined,
      checkpointPath: undefined,
    });
  });

  it('prefers the qualified name when a job carries both', () => {
    expect(
      getTrainingTelemetry(jobWithDetails({ train_lr: 0.000009, lr: 0.000005 })).learningRate
    ).toBe(0.000009);
  });

  it('drops non-finite numbers, empty strings, and wrong types', () => {
    expect(
      getTrainingTelemetry(
        jobWithDetails({
          phase: '',
          step: Number.NaN,
          train_lr: null,
          train_grad_norm: 'oops',
          checkpoint_path: '',
        })
      )
    ).toEqual({
      phase: undefined,
      step: undefined,
      maxSteps: undefined,
      numEpochs: undefined,
      epoch: undefined,
      trainLoss: undefined,
      valLoss: undefined,
      learningRate: undefined,
      gradNorm: undefined,
      checkpointPath: undefined,
    });
  });
});

describe('formatTrainingPhase', () => {
  it('maps known phases to friendly labels', () => {
    expect(formatTrainingPhase('checkpoint_saved')).toBe('Checkpoint Saved');
    expect(formatTrainingPhase('training')).toBe('Training');
  });

  it('title-cases unknown phases', () => {
    expect(formatTrainingPhase('some_new_phase')).toBe('Some New Phase');
  });
});

describe('getLossTiles', () => {
  it('dashes out both tiles when nothing has been reported', () => {
    expect(getLossTiles(undefined, true)).toEqual([
      { label: 'Final Training Loss', value: '—' },
      { label: 'Final Validation Loss', value: '—' },
    ]);
  });

  it('labels tiles "Latest" until the job reaches a terminal status', () => {
    const running = getLossTiles(undefined);
    expect(running[0].label).toBe('Latest Training Loss');
    expect(running[1].label).toBe('Latest Validation Loss');

    const finished = getLossTiles(undefined, true);
    expect(finished[0].label).toBe('Final Training Loss');
    expect(finished[1].label).toBe('Final Validation Loss');
  });

  it('builds a delta-from-start hint, tinted by improvement direction', () => {
    const tiles = getLossTiles(
      {
        metrics: {
          train_loss: [
            { step: 0, value: 1.5 },
            { step: 10, value: 1.04 },
          ],
          val_loss: [
            { step: 0, value: 1.2 },
            { step: 10, value: 1.3 },
          ],
        },
      },
      true
    );

    // Loss is lower-is-better, so a fall is "success" and a rise is "error".
    expect(tiles[0]).toEqual({
      label: 'Final Training Loss',
      value: '1.0400',
      hint: '-0.4600 from start',
      hintStatus: 'success',
    });
    expect(tiles[1]).toEqual({
      label: 'Final Validation Loss',
      value: '1.3000',
      hint: '+0.1000 from start',
      hintStatus: 'error',
    });
  });

  it('omits the delta hint when only one metric point has been reported', () => {
    const tiles = getLossTiles({ metrics: { train_loss: [{ step: 0, value: 1.5 }] } }, true);

    expect(tiles[0]).toEqual({ label: 'Final Training Loss', value: '1.5000' });
  });
});

describe('getTrainingProgressTiles', () => {
  it('dashes out both tiles when telemetry is empty', () => {
    expect(getTrainingProgressTiles({})).toEqual([
      { label: 'Steps Completed', value: '—' },
      { label: 'Epochs Completed', value: '—' },
    ]);
  });

  it('renders step and epoch progress against their totals', () => {
    expect(getTrainingProgressTiles({ step: 40, maxSteps: 100, epoch: 1, numEpochs: 3 })).toEqual([
      { label: 'Steps Completed', value: '40 / 100' },
      { label: 'Epochs Completed', value: '1 / 3' },
    ]);
  });

  it('drops the denominator when the total is unknown', () => {
    expect(getTrainingProgressTiles({ step: 40, epoch: 1 })).toEqual([
      { label: 'Steps Completed', value: '40' },
      { label: 'Epochs Completed', value: '1' },
    ]);
  });

  it('keeps a zeroth step rather than treating it as missing', () => {
    expect(getTrainingProgressTiles({ step: 0, maxSteps: 100 })[0]).toEqual({
      label: 'Steps Completed',
      value: '0 / 100',
    });
  });
});

describe('getJobDuration', () => {
  const step = (created_at: string, updated_at: string) => ({ created_at, updated_at });

  const completedSteps = [
    step('2026-08-14T13:21:46.320423', '2026-08-14T13:22:04.380207'),
    step('2026-08-14T13:22:04.395860', '2026-08-14T13:24:46.508047'),
    step('2026-08-14T13:24:46.524450', '2026-08-14T13:25:00.440349'),
    step('2026-08-14T13:25:00.500539', '2026-08-14T13:25:06.492130'),
  ];

  it('ticks live off the elapsed seconds while the job is running', () => {
    expect(getJobDuration(completedSteps, false, 72)).toBe('1m 12s');
  });

  it('spans the first step start to the last step end once terminal', () => {
    expect(getJobDuration(completedSteps, true)).toBe('00:03:20');
  });

  it('parses timestamps as UTC even when only one carries a timezone', () => {
    expect(getJobDuration([step('2025-06-25T21:41:02Z', '2025-06-25T21:42:14.242833')], true)).toBe(
      '00:01:12'
    );
  });

  it('reports a dash rather than 00:00:00 when a step never advanced', () => {
    expect(getJobDuration([step('2025-06-25T21:41:02', '2025-06-25T21:41:02')], true)).toBe('—');
  });

  it('reports a dash when there are no steps or nothing has elapsed yet', () => {
    expect(getJobDuration([], true)).toBe('—');
    expect(getJobDuration(undefined, true)).toBe('—');
    expect(getJobDuration(completedSteps, false, 0)).toBe('—');
    expect(getJobDuration(completedSteps, false, undefined)).toBe('—');
  });
});

describe('getJobStartDate', () => {
  it('anchors to the first step, not the job record', () => {
    const start = getJobStartDate([
      { created_at: '2026-08-14T13:21:46.320423', updated_at: '2026-08-14T13:22:04.380207' },
      { created_at: '2026-08-14T13:22:04.395860', updated_at: '2026-08-14T13:24:46.508047' },
    ]);

    expect(start?.toISOString()).toBe('2026-08-14T13:21:46.320Z');
  });

  it('returns undefined without steps', () => {
    expect(getJobStartDate(undefined)).toBeUndefined();
    expect(getJobStartDate([])).toBeUndefined();
  });
});

describe('getTrainingDiagnosticsTiles', () => {
  const running = { isTerminal: false, duration: '1m 12s' };
  const finished = { isTerminal: true, duration: '00:01:12' };

  it('dashes out every value when nothing has been reported, keeping the grid stable', () => {
    expect(
      getTrainingDiagnosticsTiles({}, undefined, running).map((tile) => [tile.label, tile.value])
    ).toEqual([
      ['Learning Rate', '—'],
      ['Gradient Norm', '—'],
      ['Train/Val Gap', '—'],
      ['Phase', '—'],
    ]);
  });

  it('dashes out only the values that are missing', () => {
    const tiles = getTrainingDiagnosticsTiles({ gradNorm: 1.5 }, undefined, running);

    expect(tiles).toHaveLength(4);
    expect(tiles.map((tile) => [tile.label, tile.value])).toEqual([
      ['Learning Rate', '—'],
      ['Gradient Norm', '1.5000'],
      ['Train/Val Gap', '—'],
      ['Phase', '—'],
    ]);
  });

  it('keeps a reported zero rather than mistaking it for a missing value', () => {
    const tiles = getTrainingDiagnosticsTiles({ learningRate: 0, gradNorm: 0 }, undefined, running);

    expect(tiles.slice(0, 2).map((tile) => tile.value)).toEqual(['0.00e+0', '0.0000']);
  });

  it('shows the current phase while the job is still running', () => {
    const tiles = getTrainingDiagnosticsTiles(
      { learningRate: 0.000005, gradNorm: 1.2345, phase: 'checkpoint_saved' },
      undefined,
      running
    );

    expect(tiles.map((tile) => [tile.label, tile.value])).toEqual([
      ['Learning Rate', '5.00e-6'],
      ['Gradient Norm', '1.2345'],
      ['Train/Val Gap', '—'],
      ['Phase', 'Checkpoint Saved'],
    ]);
  });

  it('swaps phase for duration once terminal, since phase then repeats the status badge', () => {
    const tiles = getTrainingDiagnosticsTiles(
      { learningRate: 0.000005, gradNorm: 1.2345, phase: 'completed' },
      undefined,
      finished
    );

    expect(tiles.map((tile) => [tile.label, tile.value])).toEqual([
      ['Learning Rate', '5.00e-6'],
      ['Gradient Norm', '1.2345'],
      ['Train/Val Gap', '—'],
      ['Duration', '00:01:12'],
    ]);
  });

  it('derives the generalization gap from the final points of both loss series', () => {
    const tiles = getTrainingDiagnosticsTiles(
      {},
      {
        metrics: {
          train_loss: [
            { step: 0, value: 5.14 },
            { step: 10, value: 1.181 },
          ],
          val_loss: [
            { step: 0, value: 1.86 },
            { step: 10, value: 1.84 },
          ],
        },
      },
      running
    );

    expect(tiles[2]).toEqual({
      label: 'Train/Val Gap',
      value: '0.6590',
      hint: 'validation - training',
    });
  });

  it('reports a negative gap when validation is ahead of training', () => {
    const tiles = getTrainingDiagnosticsTiles(
      {},
      {
        metrics: {
          train_loss: [{ step: 0, value: 1.5 }],
          val_loss: [{ step: 0, value: 1.2 }],
        },
      },
      running
    );

    expect(tiles[2]).toMatchObject({ label: 'Train/Val Gap', value: '-0.3000' });
  });

  it('dashes the gap when only one loss series is present', () => {
    const tiles = getTrainingDiagnosticsTiles(
      {},
      { metrics: { train_loss: [{ step: 0, value: 1.5 }] } },
      running
    );

    expect(tiles[2]).toMatchObject({ label: 'Train/Val Gap', value: '—' });
  });
});

describe('getFinetuningType', () => {
  it('returns an empty string when the job or training block is missing', () => {
    expect(getFinetuningType(undefined)).toBe('');
    expect(getFinetuningType(automodelJob({}))).toBe('');
    expect(getFinetuningType(unslothJob({}))).toBe('');
  });

  it('reads the finetuning type from either backend', () => {
    expect(getFinetuningType(automodelJob({ training: { finetuning_type: 'lora' } }))).toBe('lora');
    expect(getFinetuningType(unslothJob({ training: { finetuning_type: 'all_weights' } }))).toBe(
      'all_weights'
    );
  });
});

describe('formatMetricValue', () => {
  it('uses fixed notation for values a training run normally produces', () => {
    expect(formatMetricValue(0.6964)).toBe('0.6964');
    expect(formatMetricValue(-0.46)).toBe('-0.4600');
    expect(formatMetricValue(0)).toBe('0.0000');
  });

  it('switches to exponential past the magnitude that would distort the tile grid', () => {
    // toFixed(4) here would be "12000000000.0000" — 16 characters.
    expect(formatMetricValue(1.2e10)).toBe('1.20e+10');
    expect(formatMetricValue(-1.2e10)).toBe('-1.20e+10');
  });

  it('keeps fixed notation right below the threshold', () => {
    expect(formatMetricValue(999_999)).toBe('999999.0000');
    expect(formatMetricValue(1e6)).toBe('1.00e+6');
  });
});

describe('formatStepCount', () => {
  it('leaves ordinary step counts alone', () => {
    expect(formatStepCount(0)).toBe('0');
    expect(formatStepCount(210)).toBe('210');
    expect(formatStepCount(9_999)).toBe('9,999');
  });

  it('compacts counts long enough to widen the column', () => {
    expect(formatStepCount(1_234_567)).toBe('1.2M');
    expect(formatStepCount(10_000)).toBe('10K');
  });
});
