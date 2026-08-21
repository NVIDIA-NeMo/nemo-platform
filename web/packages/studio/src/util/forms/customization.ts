// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import type {
  AutomodelJobInput,
  AutomodelJobsJobRequest,
  RlJobInput,
  RlJobsJobRequest,
  UnslothJobInput,
  UnslothJobsJobRequest,
} from '@nemo/sdk/generated/customizer/schema';
import { CustomizationCreateAutomodelJobBody } from '@nemo/sdk/generated/customizer/zod/automodel-jobs';
import { CustomizationCreateRlJobBody } from '@nemo/sdk/generated/customizer/zod/rl-jobs';
import { CustomizationCreateUnslothJobBody } from '@nemo/sdk/generated/customizer/zod/unsloth-jobs';
import {
  CustomizationBackend,
  isAutomodelJob,
  isRlJob,
  type CustomizationJob,
} from '@studio/util/customizationBackend';
import { z } from 'zod';

export interface CustomizationFormFields {
  backend: CustomizationBackend;
  outputName: string;
  description: string;
  automodel: AutomodelJobInput;
  unsloth: UnslothJobInput;
  rl: RlJobInput;
}

type DatasetFieldName = 'automodel.dataset.training' | 'unsloth.dataset.path' | 'rl.dataset';

/** Each backend keeps the training dataset reference under a different path. */
export const DATASET_FIELD_BY_BACKEND: Record<CustomizationBackend, DatasetFieldName> = {
  automodel: 'automodel.dataset.training',
  unsloth: 'unsloth.dataset.path',
  rl: 'rl.dataset',
};

type ModelFieldName = 'automodel.model' | 'unsloth.model.name' | 'rl.model';

/** Likewise for the base model reference. */
export const MODEL_FIELD_BY_BACKEND: Record<CustomizationBackend, ModelFieldName> = {
  automodel: 'automodel.model',
  unsloth: 'unsloth.model.name',
  rl: 'rl.model',
};

const UNSLOTH_DEFAULT_TARGET_MODULES = [
  'q_proj',
  'k_proj',
  'v_proj',
  'o_proj',
  'gate_proj',
  'up_proj',
  'down_proj',
];

// Every value here is sent on each submit, so these must match the backend defaults
// (services/rl/src/nmp/rl/schemas.py); `max_steps` stays unset so `epochs` drives length.
const RL_DPO_DEFAULTS: RlJobInput = {
  model: '',
  dataset: '',
  training: {
    type: 'dpo',
    epochs: 1,
    learning_rate: 1e-4,
    batch_size: 32,
    micro_batch_size: 1,
    max_seq_length: 2048,
    warmup_steps: 0,
    weight_decay: 0.01,
    ref_policy_kl_penalty: 0.05,
    preference_loss_weight: 1,
    sft_loss_weight: 0,
    preference_average_log_probs: false,
    sft_average_log_probs: false,
    max_grad_norm: 1.0,
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
  },
};

export const FORM_DEFAULTS: CustomizationFormFields = {
  backend: 'automodel',
  outputName: '',
  description: '',
  automodel: {
    model: '',
    dataset: { training: '' },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: { rank: 16, alpha: 32, dropout: 0, merge: false, use_triton: true },
      max_seq_length: 2048,
      attn_implementation: 'sdpa',
    },
    schedule: { epochs: 1 },
    batch: { global_batch_size: 8, micro_batch_size: 1, sequence_packing: false },
    optimizer: {
      learning_rate: 5e-6,
      weight_decay: 0.01,
      warmup_steps: 0,
      adam_beta1: 0.9,
      adam_beta2: 0.999,
      optimizer: 'Adam',
      lr_decay_style: 'cosine',
    },
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
  },
  unsloth: {
    model: {
      name: '',
      max_seq_length: 2048,
      load_in_4bit: true,
      load_in_8bit: false,
      dtype: 'auto',
      trust_remote_code: false,
    },
    dataset: {
      path: '',
      text_field: 'text',
      apply_chat_template: false,
      packing: false,
    },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: {
        rank: 16,
        alpha: 16,
        dropout: 0,
        target_modules: UNSLOTH_DEFAULT_TARGET_MODULES,
        bias: 'none',
        use_rslora: false,
        random_state: 3407,
        init_lora_weights: true,
      },
      use_gradient_checkpointing: 'unsloth',
    },
    schedule: {
      epochs: 1,
      warmup_steps: 0,
      lr_scheduler_type: 'linear',
      logging_steps: 1,
      seed: 3407,
    },
    batch: { per_device_train_batch_size: 1, gradient_accumulation_steps: 1 },
    optimizer: { learning_rate: 2e-4, weight_decay: 0, optim: 'adamw_8bit' },
    hardware: { precision: 'bf16' },
  },
  rl: RL_DPO_DEFAULTS,
};

const automodelBodySpec = CustomizationCreateAutomodelJobBody.shape.spec;
const automodelSpecSchema = automodelBodySpec
  .omit({ output: true })
  .extend({
    model: z.string().min(1, 'Please select a model'),
    dataset: automodelBodySpec.shape.dataset.extend({
      training: z.string().min(1, 'Training dataset is required'),
    }),
  })
  .superRefine((spec, ctx) => {
    if (spec.training.training_type === 'distillation' && !spec.training.teacher_model) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Teacher model is required for distillation',
        path: ['training', 'teacher_model'],
      });
    }
  });

const unslothBodySpec = CustomizationCreateUnslothJobBody.shape.spec;
const unslothSpecSchema = unslothBodySpec.omit({ output: true }).extend({
  model: unslothBodySpec.shape.model.extend({
    name: z.string().min(1, 'Please select a model'),
  }),
  dataset: unslothBodySpec.shape.dataset.extend({
    path: z.string().min(1, 'Training dataset is required'),
  }),
});

const rlBodySpec = CustomizationCreateRlJobBody.shape.spec;
const rlSpecSchema = rlBodySpec.omit({ output: true }).extend({
  model: z.string().min(1, 'Please select a model'),
  dataset: z.string().min(1, 'Training dataset is required'),
});

export const customizationFormSchema = z
  .object({
    backend: z.nativeEnum(CustomizationBackend),
    outputName: z.string().min(1, 'Output model name is required'),
    description: z.string(),
    automodel: z.unknown(),
    unsloth: z.unknown(),
    rl: z.unknown(),
  })
  .superRefine((data, ctx) => {
    const specByBackend = {
      automodel: [automodelSpecSchema, data.automodel],
      unsloth: [unslothSpecSchema, data.unsloth],
      rl: [rlSpecSchema, data.rl],
    } as const;
    const [spec, value] = specByBackend[data.backend];
    const result = spec.safeParse(value);
    if (!result.success) {
      for (const issue of result.error.issues) {
        ctx.addIssue({ ...issue, path: [data.backend, ...issue.path] });
      }
    }
  });

export const formToAutomodelCreate = (f: CustomizationFormFields): AutomodelJobsJobRequest => {
  const { training } = f.automodel;
  const usesLora =
    training.finetuning_type === 'lora' || training.finetuning_type === 'lora_merged';
  const isDistillation = training.training_type === 'distillation';
  return {
    name: f.outputName || undefined,
    description: f.description || undefined,
    spec: {
      ...f.automodel,
      training: {
        ...training,
        lora: usesLora ? training.lora : undefined,
        teacher_model: isDistillation ? training.teacher_model || undefined : undefined,
      },
      output: { name: f.outputName, description: f.description || undefined },
    },
  };
};

export const formToRlCreate = (f: CustomizationFormFields): RlJobsJobRequest => ({
  name: f.outputName || undefined,
  description: f.description || undefined,
  spec: {
    ...f.rl,
    output: { name: f.outputName || undefined },
  },
});

export const formToUnslothCreate = (f: CustomizationFormFields): UnslothJobsJobRequest => {
  const { training } = f.unsloth;
  const usesLora = training?.finetuning_type === 'lora';
  return {
    name: f.outputName || undefined,
    description: f.description || undefined,
    spec: {
      ...f.unsloth,
      model: usesLora
        ? f.unsloth.model
        : { ...f.unsloth.model, load_in_4bit: false, load_in_8bit: false },
      hardware: { ...f.unsloth.hardware, gpus: f.unsloth.hardware?.gpus || undefined },
      training: training && { ...training, lora: usesLora ? training.lora : undefined },
      output: { name: f.outputName || undefined, description: f.description || undefined },
    },
  };
};

const stripNulls = <T>(value: T): T => {
  if (value === null) return undefined as unknown as T;
  if (Array.isArray(value)) return value.map(stripNulls) as unknown as T;
  if (typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, stripNulls(v)])
    ) as T;
  }
  return value;
};

export const jobToFormFields = (job: CustomizationJob): CustomizationFormFields => {
  if (isAutomodelJob(job)) {
    return {
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      description: job.description ?? '',
      backend: 'automodel',
      automodel: stripNulls(job.spec) as AutomodelJobInput,
    };
  }
  if (isRlJob(job)) {
    return {
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      description: job.description ?? '',
      backend: 'rl',
      rl: stripNulls(job.spec) as RlJobInput,
    };
  }
  return {
    ...FORM_DEFAULTS,
    outputName: generateDefaultName(),
    description: job.description ?? '',
    backend: 'unsloth',
    unsloth: stripNulls(job.spec) as UnslothJobInput,
  };
};
