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
  getFormattedCustomizationStatus,
  getFormattedTrainingType,
  getProgressLogs,
  getTrainingBatchSize,
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
          lr: 0.000005,
          grad_norm: 1.25,
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

  it('drops non-finite numbers, empty strings, and wrong types', () => {
    expect(
      getTrainingTelemetry(
        jobWithDetails({
          phase: '',
          step: Number.NaN,
          lr: null,
          grad_norm: 'oops',
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
