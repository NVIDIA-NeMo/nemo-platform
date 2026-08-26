// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type { RlGRPOTraining } from '@nemo/sdk/generated/customizer/schema';
import { dataset } from '@studio/mocks/datasets';
import type { AutomodelJob, RlJob, UnslothJob } from '@studio/util/customizationBackend';

const datasetUri = getURNFromNamedEntityRef(dataset)!;

const completedStatusDetails = {
  phase: 'completed',
  step: 10,
  max_steps: 10,
  num_epochs: 1,
  epoch: 1,
  percentage_done: 100,
  train_loss: 0.9,
  val_loss: 0.9,
  train_lr: 0.000005,
  train_grad_norm: 1.2345,
  checkpoint_path: 'default/output-fileset/checkpoints/step-10',
  metrics: {
    train_loss: [
      { value: 0.15, step: 2, epoch: 1 },
      { value: 0.35, step: 4, epoch: 1 },
      { value: 0.55, step: 6, epoch: 1 },
      { value: 0.85, step: 8, epoch: 1 },
      { value: 0.9, step: 10, epoch: 1 },
    ],
    val_loss: [
      { value: 0.5, step: 2, epoch: 1 },
      { value: 0.6, step: 4, epoch: 1 },
      { value: 0.7, step: 6, epoch: 1 },
      { value: 0.8, step: 8, epoch: 1 },
      { value: 0.9, step: 10, epoch: 1 },
    ],
  },
  status_logs: [
    { updated_at: '2025-10-24T15:13:17', message: 'created' },
    {
      updated_at: '2025-10-24T15:13:17.175399',
      message: 'TrainingJobPending',
      detail: 'The training job is pending',
    },
    { updated_at: '2025-10-24T15:13:33', message: 'TrainingJobRunning' },
    { updated_at: '2025-10-24T15:16:18', message: 'TrainingJobCompleted' },
  ],
};

/** Automodel distillation job. */
export const customizationJob1: AutomodelJob = {
  id: 'cust-4k8XJ8fRYtQT8NTBbjxAqk',
  name: 'meta-llama-3.2-1b-distillation-job',
  created_at: '2025-06-25T21:41:02.067430',
  updated_at: '2025-06-25T21:42:14.242833',
  workspace: 'default',
  project: 'default/project-QRpQtqLB4CJ2fUxKSCWsFX',
  ownership: { created_by: '', access_policies: {} },
  description: 'This is a test customization job',
  spec: {
    model: 'meta/llama-3.2-1b-distillation@v1.0.0+A100',
    dataset: { training: datasetUri },
    training: {
      training_type: 'distillation',
      finetuning_type: 'lora',
      lora: { rank: 16, alpha: 32, dropout: 0, merge: false, target_modules: ['q_proj', 'v_proj'] },
      max_seq_length: 2048,
      precision: 'bf16',
      teacher_model: 'qwen/qwen-2_5-72b-instruct',
      teacher_precision: 'bf16',
      distillation_ratio: 0.5,
      distillation_temperature: 2,
      offload_teacher: false,
    },
    schedule: { epochs: 1, max_steps: 1000, seed: 42 },
    batch: { global_batch_size: 8, micro_batch_size: 1, sequence_packing: false },
    optimizer: {
      learning_rate: 0.0001,
      weight_decay: 0.01,
      adam_beta1: 0.9,
      adam_beta2: 0.999,
      warmup_steps: 100,
    },
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
    output: {
      name: 'default/meta-llama-3.2-1b-instruct-distillation@cust-4k8XJ8fRYtQT8NTBbjxAqk',
      type: 'model',
      fileset: 'default/output-fileset',
    },
  },
  status: 'completed',
  status_details: completedStatusDetails,
};

/** Automodel SFT + LoRA job. */
export const customizationJob2: AutomodelJob = {
  id: 'cust-DTDYY777TapJkJwkq6jMDD',
  name: 'meta-llama-3.1-8b-sft-lora-job',
  created_at: '2025-06-04T19:10:17.026494',
  updated_at: '2025-06-04T19:15:26.480239',
  workspace: 'default',
  project: 'default/project-QRpQtqLB4CJ2fUxKSCWsFX',
  ownership: { created_by: '', access_policies: {} },
  spec: {
    model: 'meta/llama-3.1-8b-instruct@v1.0.0+A100',
    dataset: { training: datasetUri },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: {
        rank: 32,
        alpha: 16,
        dropout: 0.1,
        merge: false,
        target_modules: ['q_proj', 'v_proj'],
      },
      max_seq_length: 2048,
    },
    schedule: { epochs: 1, max_steps: 1000, seed: 42 },
    batch: { global_batch_size: 8, micro_batch_size: 1, sequence_packing: false },
    optimizer: {
      learning_rate: 0.0001,
      weight_decay: 0.01,
      adam_beta1: 0.9,
      adam_beta2: 0.999,
      warmup_steps: 0,
    },
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
    output: {
      name: 'default/meta-llama-3.1-8b-instruct-academic-spoonbill-lora@cust-DTDYY777TapJkJwkq6jMDD',
      type: 'adapter',
      fileset: 'default/output-fileset',
    },
  },
  status: 'completed',
  status_details: { phase: 'completed', step: 44, max_steps: 44, epoch: 1, percentage_done: 100 },
};

/** Unsloth SFT + LoRA job. */
export const customizationJob3: UnslothJob = {
  id: 'cust-7hyykExVYdj9j8wMg6UKe2',
  name: 'meta-llama-3.1-8b-unsloth-sft-lora-job',
  created_at: '2025-06-04T19:10:16.633103',
  updated_at: '2025-06-04T19:34:26.406896',
  workspace: 'default',
  project: 'default/project-QRpQtqLB4CJ2fUxKSCWsFX',
  ownership: { created_by: '', access_policies: {} },
  spec: {
    model: {
      name: 'meta/llama-3.1-8b-instruct@v1.0.0+A100',
      max_seq_length: 2048,
      load_in_4bit: true,
      load_in_8bit: false,
      dtype: 'auto',
      trust_remote_code: false,
    },
    dataset: { path: datasetUri, text_field: 'text', apply_chat_template: false, packing: false },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: {
        rank: 16,
        alpha: 16,
        dropout: 0,
        target_modules: ['q_proj', 'k_proj', 'v_proj', 'o_proj'],
        bias: 'none',
        use_rslora: false,
        random_state: 3407,
      },
      use_gradient_checkpointing: 'unsloth',
    },
    schedule: {
      epochs: 3,
      warmup_steps: 5,
      lr_scheduler_type: 'linear',
      logging_steps: 1,
      seed: 3407,
    },
    batch: { per_device_train_batch_size: 2, gradient_accumulation_steps: 4 },
    optimizer: { learning_rate: 0.0002, weight_decay: 0, optim: 'adamw_8bit' },
    hardware: { gpus: '0', precision: 'bf16' },
    output: {
      name: 'default/meta-llama-3.1-8b-instruct-unsloth-lora@cust-7hyykExVYdj9j8wMg6UKe2',
      type: 'adapter',
      save_method: 'lora',
      fileset: 'default/output-fileset',
    },
  },
  status: 'completed',
  status_details: { phase: 'completed', step: 44, max_steps: 44, epoch: 3, percentage_done: 100 },
};

const TRAINING_STEPS = [1, 100, 200, 300, 400, 500];

const series = (values: number[]) =>
  values.map((value, index) => ({ value, step: TRAINING_STEPS[index], epoch: 1 }));

/**
 * Names taken from the golden test pinning NeMo-RL's logged dict, since the whole GRPO overview
 * reads through them. `train_total_reward/stddev` is absent because a real run has no history.
 */
export const grpoStatusDetails = {
  phase: 'completed',
  step: 500,
  max_steps: 500,
  num_epochs: 1,
  epoch: 1,
  percentage_done: 100,
  checkpoint_path: 'default/grpo-output-fileset/checkpoints/step-500',
  train_reward: 0.617,
  val_accuracy: 0.58,
  train_truncation_rate: 0.041,
  'train_total_reward/mean': 0.617,
  'train_total_reward/stddev': 0.486,
  metrics: {
    train_loss: [],
    val_loss: [],
    train_reward: series([0.18, 0.34, 0.45, 0.52, 0.58, 0.617]),
    val_accuracy: [
      { value: 0.31, step: 100, epoch: 1 },
      { value: 0.49, step: 300, epoch: 1 },
      { value: 0.58, step: 500, epoch: 1 },
    ],
    train_truncation_rate: series([0.09, 0.072, 0.061, 0.05, 0.044, 0.041]),
    train_gen_kl_error: series([0.00012, 0.00028, 0.00039, 0.00047, 0.00051, 0.00054]),
    train_token_mult_prob_error: series([1.001, 1.002, 1.003, 1.004, 1.004, 1.004]),
    train_approx_entropy: series([0.98, 0.74, 0.55, 0.43, 0.36, 0.31]),
    'train_advantages/mean': series([0.001, 0.002, 0.003, 0.002, 0.004, 0.003]),
    train_kl_penalty: series([0, 0, 0, 0, 0, 0]),
    'train_gen_tokens_per_sample/mean': series([412.5, 498.1, 561.4, 612.9, 664.2, 689.3]),
  },
};

/** The same run, once the backend also records the reward spread — the chart then draws a band. */
export const grpoStatusDetailsWithSpread = {
  ...grpoStatusDetails,
  metrics: {
    ...grpoStatusDetails.metrics,
    'train_total_reward/stddev': series([0.09, 0.14, 0.17, 0.19, 0.2, 0.21]),
  },
};

const grpoTraining: RlGRPOTraining = {
  type: 'grpo',
  finetuning_type: 'all_weights',
  epochs: 1,
  max_steps: 500,
  batch_size: 64,
  micro_batch_size: 1,
  max_seq_length: 4096,
  learning_rate: 0.000001,
  num_generations_per_prompt: 8,
  num_prompts_per_step: 8,
  temperature: 1,
  normalize_rewards: true,
  overlong_filtering: true,
  max_rollout_turns: 1,
  ref_policy_kl_penalty: 0,
  parallelism: { num_nodes: 1, num_gpus_per_node: 8, tensor_parallel_size: 4 },
};

/** NeMo-RL GRPO job against a NeMo Gym environment. */
export const grpoCustomizationJob: RlJob = {
  id: 'cust-9pQm2VxTgHs4RbNkLd7Wce',
  name: 'grpo-qwen-math-0812',
  created_at: '2026-08-12T14:02:11.412000',
  updated_at: '2026-08-12T19:48:52.901000',
  workspace: 'default',
  project: 'default/project-QRpQtqLB4CJ2fUxKSCWsFX',
  ownership: { created_by: '', access_policies: {} },
  description: 'GRPO against the math verifier environment',
  spec: {
    model: 'qwen/qwen2.5-7b-instruct',
    dataset: datasetUri,
    environment: 'default/math-verifier-env',
    training: grpoTraining,
    output: {
      name: 'default/qwen2.5-7b-instruct-grpo-math@cust-9pQm2VxTgHs4RbNkLd7Wce',
      type: 'model',
      fileset: 'default/grpo-output-fileset',
    },
  },
  status: 'completed',
  status_details: grpoStatusDetails,
};

export const customizationJobs = [
  customizationJob1,
  customizationJob2,
  customizationJob3,
  grpoCustomizationJob,
];

export const customizationJobSteps = [
  {
    id: 'step-download',
    name: 'model-and-dataset-download',
    status: 'completed',
    status_details: { message: 'completed' },
    error_details: {},
    tasks: [],
    created_at: '2025-06-25T21:41:02.100000',
    updated_at: '2025-06-25T21:41:12.100000',
  },
  {
    id: 'step-training',
    name: 'training',
    status: 'completed',
    status_details: { message: 'completed' },
    error_details: {},
    tasks: [],
    created_at: '2025-06-25T21:41:12.100000',
    updated_at: '2025-06-25T21:42:02.100000',
  },
  {
    id: 'step-upload',
    name: 'model-upload',
    status: 'completed',
    status_details: { message: 'completed' },
    error_details: {},
    tasks: [],
    created_at: '2025-06-25T21:42:02.100000',
    updated_at: '2025-06-25T21:42:10.100000',
  },
  {
    id: 'step-entity',
    name: 'model-entity-creation',
    status: 'completed',
    status_details: { message: 'completed' },
    error_details: {},
    tasks: [],
    created_at: '2025-06-25T21:42:10.100000',
    updated_at: '2025-06-25T21:42:14.242833',
  },
];
