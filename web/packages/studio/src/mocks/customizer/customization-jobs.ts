// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type { AutomodelJob, UnslothJob } from '@nemo/sdk/vendored/customizer/schema';
import { dataset } from '@studio/mocks/datasets';

const datasetUri = getURNFromNamedEntityRef(dataset)!;

const completedStatusDetails = {
  phase: 'completed',
  step: 10,
  max_steps: 10,
  epoch: 1,
  percentage_done: 100,
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

export const customizationJobs = [customizationJob1, customizationJob2, customizationJob3];
