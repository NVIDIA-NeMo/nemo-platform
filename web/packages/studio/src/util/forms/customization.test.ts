// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

vi.mock('@nemo/common/src/namedEntity', () => ({
  getURNFromNamedEntityRef: vi.fn(),
}));

import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { FilesetPurpose, type FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import {
  formToCustomizationCreate,
  type NewCustomizationFormFields,
} from '@studio/util/forms/customization';

function makeTestFileset(overrides: Partial<FilesetOutput> = {}): FilesetOutput {
  return {
    id: 'ds-1',
    name: 'my-dataset',
    workspace: 'default',
    description: '',
    purpose: FilesetPurpose.dataset,
    storage: { type: 'local', path: '/data' },
    metadata: {},
    custom_fields: {},
    project: 'default',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

const baseFormData: NewCustomizationFormFields = {
  project: 'my-project',
  base_model_id: 'model-123',
  description: 'A test customization',
  training_type: 'sft',
  finetuning_type: 'sft',
  batch_size: 8,
  epochs: 3,
  learning_rate: 0.001,
  hidden_dropout: 0,
  attention_dropout: 0,
  ffn_dropout: 0,
  weight_decay: 0.01,
  virtual_tokens: 0,
  adapter_dim: 16,
  adapter_dropout: 0.1,
};

describe('formToCustomizationCreate', () => {
  beforeEach(() => {
    vi.mocked(getURNFromNamedEntityRef).mockReset();
  });

  it('includes peft config when finetuning_type is lora', () => {
    const formData: NewCustomizationFormFields = {
      ...baseFormData,
      finetuning_type: 'lora',
      adapter_dim: 32,
      adapter_dropout: 0.05,
    };

    const result = formToCustomizationCreate(formData);

    expect(result.spec.training).toEqual({
      type: 'sft',
      batch_size: 8,
      epochs: 3,
      learning_rate: 0.001,
      weight_decay: 0.01,
      peft: {
        type: 'lora',
        rank: 32,
        dropout: 0.05,
      },
    });
  });

  it('excludes peft config when finetuning_type is not lora', () => {
    const result = formToCustomizationCreate(baseFormData);

    expect(result.spec.training).toEqual({
      type: 'sft',
      batch_size: 8,
      epochs: 3,
      learning_rate: 0.001,
      weight_decay: 0.01,
    });
    expect(result.spec.training).not.toHaveProperty('peft');
  });

  it('returns empty string for dataset when dataset is not provided', () => {
    const result = formToCustomizationCreate(baseFormData);

    expect(result.spec.dataset).toBe('');
  });

  it('uses getURNFromNamedEntityRef for dataset when provided', () => {
    const datasetUrn = 'default/my-dataset';
    vi.mocked(getURNFromNamedEntityRef).mockReturnValue(datasetUrn);

    const dataset = makeTestFileset();
    const formData: NewCustomizationFormFields = {
      ...baseFormData,
      dataset,
    };

    const result = formToCustomizationCreate(formData);

    expect(getURNFromNamedEntityRef).toHaveBeenCalledWith(dataset);
    expect(result.spec.dataset).toBe(datasetUrn);
  });

  it('returns empty string when getURNFromNamedEntityRef returns falsy', () => {
    vi.mocked(getURNFromNamedEntityRef).mockReturnValue(undefined);

    const formData: NewCustomizationFormFields = {
      ...baseFormData,
      dataset: makeTestFileset(),
    };

    const result = formToCustomizationCreate(formData);

    expect(result.spec.dataset).toBe('');
  });

  it('maps project and description to the result', () => {
    const result = formToCustomizationCreate(baseFormData);

    expect(result.project).toBe('my-project');
    expect(result.description).toBe('A test customization');
    expect(result.spec.model).toBe('model-123');
  });
});
