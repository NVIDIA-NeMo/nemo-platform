// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AutomodelJobInput, UnslothJobInput } from '@nemo/sdk/vendored/customizer/schema';
import { z } from 'zod';

export interface CustomizationFormFields {
  backend: 'automodel' | 'unsloth';
  outputName: string;
  description: string;
  automodel: AutomodelJobInput['spec'];
  unsloth: UnslothJobInput['spec'];
}

const UNSLOTH_DEFAULT_TARGET_MODULES = [
  'q_proj',
  'k_proj',
  'v_proj',
  'o_proj',
  'gate_proj',
  'up_proj',
  'down_proj',
];

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
};

const automodelSpecSchema = z
  .object({
    model: z.string().min(1, 'Please select a model'),
    dataset: z.object({
      training: z.string().min(1, 'Training dataset is required'),
      validation: z.string().optional(),
    }),
    training: z.object({
      training_type: z.enum(['sft', 'distillation']),
      finetuning_type: z.enum(['lora', 'all_weights', 'lora_merged']),
      max_seq_length: z.number().int().positive(),
      teacher_model: z.string().optional(),
      lora: z
        .object({
          rank: z.number().int().positive(),
          alpha: z.number().int().positive(),
          dropout: z.number().min(0).max(1),
          merge: z.boolean(),
        })
        .optional(),
    }),
    schedule: z.object({ epochs: z.number().int().positive() }).optional(),
    batch: z
      .object({
        global_batch_size: z.number().int().positive(),
        micro_batch_size: z.number().int().positive(),
        sequence_packing: z.boolean(),
      })
      .optional(),
    optimizer: z
      .object({
        learning_rate: z.number().positive(),
        weight_decay: z.number().min(0),
        warmup_steps: z.number().int().min(0),
        adam_beta1: z.number(),
        adam_beta2: z.number(),
        min_learning_rate: z.number().min(0).optional(),
      })
      .optional(),
    parallelism: z
      .object({
        num_nodes: z.number().int().positive(),
        num_gpus_per_node: z.number().int().positive(),
        tensor_parallel_size: z.number().int().positive(),
        pipeline_parallel_size: z.number().int().positive(),
        context_parallel_size: z.number().int().positive(),
        sequence_parallel: z.boolean(),
      })
      .optional(),
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

const unslothSpecSchema = z.object({
  model: z.object({
    name: z.string().min(1, 'Please select a model'),
    max_seq_length: z.number().int().positive(),
    load_in_4bit: z.boolean(),
    load_in_8bit: z.boolean(),
    dtype: z.enum(['auto', 'bfloat16', 'float16', 'float32']),
    trust_remote_code: z.boolean(),
  }),
  dataset: z.object({
    path: z.string().min(1, 'Training dataset is required'),
    validation_path: z.string().optional(),
  }),
  training: z
    .object({
      finetuning_type: z.enum(['lora', 'all_weights']),
      lora: z
        .object({
          rank: z.number().int().positive(),
          alpha: z.number().int().positive(),
          dropout: z.number().min(0).max(1),
          target_modules: z.array(z.string()),
          bias: z.enum(['none', 'all', 'lora_only']),
          use_rslora: z.boolean(),
          random_state: z.number().int(),
        })
        .optional(),
    })
    .optional(),
  schedule: z
    .object({
      epochs: z.number().int().positive(),
      warmup_steps: z.number().int().min(0),
      lr_scheduler_type: z.enum([
        'linear',
        'cosine',
        'constant',
        'constant_with_warmup',
        'cosine_with_restarts',
      ]),
      logging_steps: z.number().int().positive(),
      seed: z.number().int(),
    })
    .optional(),
  batch: z
    .object({
      per_device_train_batch_size: z.number().int().positive(),
      gradient_accumulation_steps: z.number().int().positive(),
    })
    .optional(),
  optimizer: z
    .object({
      learning_rate: z.number().positive(),
      weight_decay: z.number().min(0),
      optim: z.enum(['adamw_torch', 'adamw_torch_fused', 'adamw_8bit', 'paged_adamw_8bit', 'sgd']),
    })
    .optional(),
  hardware: z
    .object({ gpus: z.string().optional(), precision: z.enum(['bf16', 'fp16']) })
    .optional(),
});

export const customizationFormSchema = z
  .object({
    backend: z.enum(['automodel', 'unsloth']),
    outputName: z.string().min(1, 'Output model name is required'),
    description: z.string(),
    automodel: z.unknown(),
    unsloth: z.unknown(),
  })
  .superRefine((data, ctx) => {
    const spec = data.backend === 'automodel' ? automodelSpecSchema : unslothSpecSchema;
    const value = data.backend === 'automodel' ? data.automodel : data.unsloth;
    const result = spec.safeParse(value);
    if (!result.success) {
      for (const issue of result.error.issues) {
        ctx.addIssue({ ...issue, path: [data.backend, ...issue.path] });
      }
    }
  });

export const formToAutomodelCreate = (f: CustomizationFormFields): AutomodelJobInput => {
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

export const formToUnslothCreate = (f: CustomizationFormFields): UnslothJobInput => {
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
