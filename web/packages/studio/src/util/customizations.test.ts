// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

vi.mock('@nemo/common/src/namedEntity', () => ({
  getURNFromNamedEntityRef: vi.fn(),
}));

import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import type {
  CustomizationJob,
  CustomizationJobStatusDetails,
  FinetuningType,
} from '@nemo/sdk/vendored/customizer/schema';
import {
  formatFinetuningType,
  getBaseModel,
  getCustomizationConfigurationName,
  getCustomizationConfigurationURN,
  getCustomizationTrainingProgress,
  getCustomizationTrainingSteps,
  getDatasetName,
  getFailureMessage,
  getFormattedCustomizationStatus,
  getFormattedTrainingType,
  getProgressLogs,
} from '@studio/util/customizations';

describe('getFormattedTrainingType', () => {
  it('Returns the correctly formatted training type', () => {
    expect(getFormattedTrainingType('lora')).toEqual('LoRA');
    expect(getFormattedTrainingType('sft')).toEqual('SFT');
  });
});

describe('formatFinetuningType', () => {
  it.each([
    ['lora', 'LoRA'],
    ['lora_merged', 'LoRA Merged'],
    ['all_weights', 'All Weights'],
    ['last_layer', 'Last Layer'],
    ['top_layers', 'Top Layers'],
    ['gradual_unfreezing', 'Gradual Unfreezing'],
    ['bias_only', 'Bias Only'],
    ['attention_only', 'Attention Only'],
    ['qlora', 'QLoRA'],
    ['adalora', 'AdaLoRA'],
    ['dora', 'DoRA'],
    ['lora_plus', 'LoRA+'],
    ['prompt_tuning', 'Prompt Tuning'],
    ['prefix_tuning', 'Prefix Tuning'],
    ['p_tuning', 'P-Tuning'],
    ['p_tuning_v2', 'P-Tuning v2'],
    ['soft_prompt', 'Soft Prompt'],
    ['ppo', 'PPO'],
    ['dpo', 'DPO'],
    ['cdpo', 'cDPO'],
    ['ipo', 'IPO'],
    ['orpo', 'ORPO'],
    ['kto', 'KTO'],
    ['rrhf', 'RRHF'],
    ['grpo', 'GRPO'],
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

  it('returns model from spec', () => {
    const job = { spec: { model: 'my-model' } } as unknown as CustomizationJob;
    expect(getBaseModel(job)).toBe('my-model');
  });

  it('returns empty string when spec.model is missing', () => {
    const job = { spec: {} } as unknown as CustomizationJob;
    expect(getBaseModel(job)).toBe('');
  });
});

describe('getDatasetName', () => {
  it('returns string dataset URI', () => {
    const job = { spec: { dataset: 'urn:dataset:abc' } } as unknown as CustomizationJob;
    expect(getDatasetName(job)).toBe('urn:dataset:abc');
  });

  it('returns empty string for non-string dataset', () => {
    const job = { spec: { dataset: 123 } } as unknown as CustomizationJob;
    expect(getDatasetName(job)).toBe('');
  });

  it('returns empty string when dataset is undefined', () => {
    const job = { spec: {} } as unknown as CustomizationJob;
    expect(getDatasetName(job)).toBe('');
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
    const job = {
      status_details: {},
      spec: { training: { epochs: 5 } },
    } as unknown as CustomizationJob;
    expect(getCustomizationTrainingProgress(job)).toBe('');
  });

  it('returns formatted progress string', () => {
    const job = {
      status_details: { epoch: 2, percentage_done: 40 },
      spec: { training: { epochs: 5 } },
    } as unknown as CustomizationJob;
    expect(getCustomizationTrainingProgress(job)).toBe('2/5 (40%)');
  });

  it('handles missing epoch gracefully', () => {
    const job = {
      status_details: { percentage_done: 60 },
      spec: { training: { epochs: 3 } },
    } as unknown as CustomizationJob;
    expect(getCustomizationTrainingProgress(job)).toBe('0/3 (60%)');
  });
});

describe('getCustomizationConfigurationName', () => {
  it('returns empty string for falsy input', () => {
    expect(getCustomizationConfigurationName('' as unknown as ModelEntity)).toBe('');
  });

  it('returns string input as-is', () => {
    expect(getCustomizationConfigurationName('my-config')).toBe('my-config');
  });

  it('returns name from ModelEntity', () => {
    const model = { name: 'test-model' } as unknown as ModelEntity;
    expect(getCustomizationConfigurationName(model)).toBe('test-model');
  });
});

describe('getCustomizationConfigurationURN', () => {
  beforeEach(() => {
    vi.mocked(getURNFromNamedEntityRef).mockReset();
  });

  it('returns undefined when customization is undefined', () => {
    expect(getCustomizationConfigurationURN(undefined)).toBeUndefined();
  });

  it('returns undefined when model is missing', () => {
    const job = { spec: {} } as unknown as CustomizationJob;
    expect(getCustomizationConfigurationURN(job)).toBeUndefined();
  });

  it('returns string model as a resource ref', () => {
    const job = { spec: { model: 'default/model-123' } } as unknown as CustomizationJob;
    expect(getCustomizationConfigurationURN(job)).toBe('default/model-123');
  });

  it('returns undefined for string model that is not a resource ref', () => {
    const job = { spec: { model: 'urn:model:123' } } as unknown as CustomizationJob;
    expect(getCustomizationConfigurationURN(job)).toBeUndefined();
  });

  it('calls getURNFromNamedEntityRef for object model', () => {
    vi.mocked(getURNFromNamedEntityRef).mockReturnValue('default/model-456' as never);
    const modelObj = { name: 'obj-model' };
    const job = { spec: { model: modelObj } } as unknown as CustomizationJob;
    expect(getCustomizationConfigurationURN(job)).toBe('default/model-456');
    expect(getURNFromNamedEntityRef).toHaveBeenCalledWith(modelObj);
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
