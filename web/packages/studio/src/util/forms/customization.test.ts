// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FORM_DEFAULTS,
  customizationFormSchema,
  formToAutomodelCreate,
  formToUnslothCreate,
  type CustomizationFormFields,
} from '@studio/util/forms/customization';

// Deep-clone the defaults so per-test mutations (e.g. flipping finetuning_type)
// never leak through shared nested references into FORM_DEFAULTS or other tests.
/** A fully-valid automodel form value (model + training dataset filled). */
const validAutomodel = (): CustomizationFormFields => {
  const data = structuredClone(FORM_DEFAULTS);
  data.backend = 'automodel';
  data.outputName = 'my-output';
  data.automodel.model = 'default/llama-3.1-8b';
  data.automodel.dataset = { training: 'default/train-ds' };
  return data;
};

/** A fully-valid unsloth form value (model + path filled). */
const validUnsloth = (): CustomizationFormFields => {
  const data = structuredClone(FORM_DEFAULTS);
  data.backend = 'unsloth';
  data.outputName = 'my-output';
  data.unsloth.model.name = 'default/qwen3-1.7b';
  data.unsloth.dataset.path = 'default/train-ds';
  return data;
};

const messages = (data: CustomizationFormFields): string[] => {
  const result = customizationFormSchema.safeParse(data);
  return result.success ? [] : result.error.issues.map((i) => i.message);
};

describe('customizationFormSchema', () => {
  it('accepts a valid automodel form', () => {
    expect(customizationFormSchema.safeParse(validAutomodel()).success).toBe(true);
  });

  it('accepts a valid unsloth form', () => {
    expect(customizationFormSchema.safeParse(validUnsloth()).success).toBe(true);
  });

  it('requires an output model name', () => {
    const data = { ...validAutomodel(), outputName: '' };
    expect(messages(data)).toContain('Output model name is required');
  });

  describe('active-backend-only validation', () => {
    // Regression: the form keeps both sub-objects in state; switching backend
    // unmounts the other backend's fields. Only the selected backend must be valid.
    it('ignores an empty automodel subtree when unsloth is selected', () => {
      const data = validUnsloth();
      data.automodel = {
        ...data.automodel,
        model: '',
        dataset: { training: '' },
      };
      expect(customizationFormSchema.safeParse(data).success).toBe(true);
    });

    it('ignores an empty unsloth subtree when automodel is selected', () => {
      const data = validAutomodel();
      data.unsloth = {
        ...data.unsloth,
        model: { ...data.unsloth.model, name: '' },
        dataset: { ...data.unsloth.dataset, path: '' },
      };
      expect(customizationFormSchema.safeParse(data).success).toBe(true);
    });
  });

  describe('automodel required fields', () => {
    it('requires a model', () => {
      const data = validAutomodel();
      data.automodel.model = '';
      expect(messages(data)).toContain('Please select a model');
    });

    it('requires a training dataset', () => {
      const data = validAutomodel();
      data.automodel.dataset.training = '';
      expect(messages(data)).toContain('Training dataset is required');
    });

    it('requires a teacher model for distillation', () => {
      const data = validAutomodel();
      data.automodel.training.training_type = 'distillation';
      data.automodel.training.teacher_model = '';
      expect(messages(data)).toContain('Teacher model is required for distillation');
    });

    it('does not require a teacher model for sft', () => {
      const data = validAutomodel();
      data.automodel.training.training_type = 'sft';
      data.automodel.training.teacher_model = '';
      expect(customizationFormSchema.safeParse(data).success).toBe(true);
    });
  });

  describe('unsloth required fields', () => {
    it('requires a model', () => {
      const data = validUnsloth();
      data.unsloth.model.name = '';
      expect(messages(data)).toContain('Please select a model');
    });

    it('requires a training dataset path', () => {
      const data = validUnsloth();
      data.unsloth.dataset.path = '';
      expect(messages(data)).toContain('Training dataset is required');
    });
  });
});

describe('formToAutomodelCreate', () => {
  it('maps output name and description onto the job and spec.output', () => {
    const data = validAutomodel();
    data.description = 'my desc';
    const result = formToAutomodelCreate(data);
    expect(result.name).toBe('my-output');
    expect(result.description).toBe('my desc');
    expect(result.spec.output).toEqual({ name: 'my-output', description: 'my desc' });
  });

  it('omits blank job name/description but always sets the required spec.output.name', () => {
    // The top-level job name is omitted when blank, but automodel requires
    // spec.output.name, so it carries the (validation-guaranteed non-empty)
    // output name verbatim.
    const data = validAutomodel();
    data.outputName = '';
    data.description = '';
    const result = formToAutomodelCreate(data);
    expect(result.name).toBeUndefined();
    expect(result.description).toBeUndefined();
    expect(result.spec.output).toEqual({ name: '', description: undefined });
  });

  it('keeps lora params for lora finetuning', () => {
    const data = validAutomodel();
    data.automodel.training.finetuning_type = 'lora';
    expect(formToAutomodelCreate(data).spec.training.lora).toBeDefined();
  });

  it('keeps lora params for lora_merged finetuning', () => {
    const data = validAutomodel();
    data.automodel.training.finetuning_type = 'lora_merged';
    expect(formToAutomodelCreate(data).spec.training.lora).toBeDefined();
  });

  it('drops lora params for all_weights finetuning', () => {
    const data = validAutomodel();
    data.automodel.training.finetuning_type = 'all_weights';
    expect(formToAutomodelCreate(data).spec.training.lora).toBeUndefined();
  });

  it('sends the backend-default use_triton flag for lora runs', () => {
    // Backend defaults use_triton to true; the form must not silently send false.
    const spec = formToAutomodelCreate(validAutomodel()).spec;
    expect(spec.training.lora?.use_triton).toBe(true);
  });

  it('seeds the backend-default enum knobs so the UI matches the backend', () => {
    const spec = formToAutomodelCreate(validAutomodel()).spec;
    expect(spec.training.attn_implementation).toBe('sdpa');
    expect(spec.optimizer?.optimizer).toBe('Adam');
    expect(spec.optimizer?.lr_decay_style).toBe('cosine');
  });

  it('passes through advanced automodel fields set on the form', () => {
    const data = validAutomodel();
    data.automodel.batch = {
      ...data.automodel.batch!,
      sequence_packing_max_samples: 500,
    };
    data.automodel.training.lora = {
      ...data.automodel.training.lora!,
      exclude_modules: ['*.out_proj'],
    };
    const spec = formToAutomodelCreate(data).spec;
    expect(spec.batch?.sequence_packing_max_samples).toBe(500);
    expect(spec.training.lora?.exclude_modules).toEqual(['*.out_proj']);
  });

  it('includes teacher_model only for distillation', () => {
    const distill = validAutomodel();
    distill.automodel.training.training_type = 'distillation';
    distill.automodel.training.teacher_model = 'default/teacher';
    expect(formToAutomodelCreate(distill).spec.training.teacher_model).toBe('default/teacher');

    const sft = validAutomodel();
    sft.automodel.training.training_type = 'sft';
    sft.automodel.training.teacher_model = 'default/teacher'; // stale value from a prior distillation selection
    expect(formToAutomodelCreate(sft).spec.training.teacher_model).toBeUndefined();
  });
});

describe('formToUnslothCreate', () => {
  it('always supplies the fixed dataset fields the UI does not expose', () => {
    const spec = formToUnslothCreate(validUnsloth()).spec;
    expect(spec.dataset.text_field).toBe('text');
    expect(spec.dataset.packing).toBe(false);
    expect(spec.training?.use_gradient_checkpointing).toBe('unsloth');
  });

  it('preserves the detected apply_chat_template flag', () => {
    const data = validUnsloth();
    data.unsloth.dataset.apply_chat_template = true;
    expect(formToUnslothCreate(data).spec.dataset.apply_chat_template).toBe(true);
  });

  it('omits gpus when blank', () => {
    const data = validUnsloth();
    data.unsloth.hardware = { ...data.unsloth.hardware!, gpus: '' };
    expect(formToUnslothCreate(data).spec.hardware?.gpus).toBeUndefined();
  });

  it('keeps gpus when provided', () => {
    const data = validUnsloth();
    data.unsloth.hardware = { ...data.unsloth.hardware!, gpus: '0,1' };
    expect(formToUnslothCreate(data).spec.hardware?.gpus).toBe('0,1');
  });

  it('keeps lora params for lora finetuning', () => {
    const data = validUnsloth();
    data.unsloth.training!.finetuning_type = 'lora';
    expect(formToUnslothCreate(data).spec.training?.lora).toBeDefined();
  });

  it('drops lora params for all_weights finetuning', () => {
    const data = validUnsloth();
    data.unsloth.training!.finetuning_type = 'all_weights';
    expect(formToUnslothCreate(data).spec.training?.lora).toBeUndefined();
  });

  it('disables quantization for all_weights finetuning', () => {
    // The unsloth backend rejects finetuning_type='all_weights' with 4-bit/8-bit
    // loading, so the mapper must force both off for full-weight runs.
    const data = validUnsloth();
    data.unsloth.training!.finetuning_type = 'all_weights';
    data.unsloth.model.load_in_4bit = true;
    const spec = formToUnslothCreate(data).spec;
    expect(spec.model.load_in_4bit).toBe(false);
    expect(spec.model.load_in_8bit).toBe(false);
  });

  it('keeps quantization for lora finetuning', () => {
    const data = validUnsloth();
    data.unsloth.training!.finetuning_type = 'lora';
    data.unsloth.model.load_in_4bit = true;
    expect(formToUnslothCreate(data).spec.model.load_in_4bit).toBe(true);
  });
});
