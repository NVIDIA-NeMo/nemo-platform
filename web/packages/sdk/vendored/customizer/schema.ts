// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// TEMP: customizer-specific schema types inlined while the customizer SDK is being rebuilt.
// The customizer BE is now a hub + per-backend contributor architecture (automodel, unsloth),
// each exposing its own job collection under /apis/customization/v2/workspaces/{workspace}/{backend}/jobs.
// These are READ-ONLY types for the job details page; the create/form path was removed.
// Restore SDK imports (`@nemo/sdk/generated/platform/schema`) once the SDK regenerates with customizer support.

// Shared types still live in the SDK — re-export from there.
export type { PlatformJobStatus, PaginationData, SecretRef } from '../../generated/platform/schema';

import type { PlatformJobStatus, SecretRef } from '../../generated/platform/schema';

// ----- CustomizationBackend -----
// Discriminates which training contributor produced a job. Not a wire field — derived from the
// job spec shape (automodel specs carry `parallelism`, unsloth specs carry `hardware`).
export type CustomizationBackend = (typeof CustomizationBackend)[keyof typeof CustomizationBackend];

export const CustomizationBackend = {
  automodel: 'automodel',
  unsloth: 'unsloth',
} as const;

// ----- Precision -----
export type Precision = (typeof Precision)[keyof typeof Precision];

export const Precision = {
  fp8: 'fp8',
  bf16: 'bf16',
  fp16: 'fp16',
  fp32: 'fp32',
} as const;

// ----- Shared output + integrations -----

export type OutputNameType = (typeof OutputNameType)[keyof typeof OutputNameType];

export const OutputNameType = {
  adapter: 'adapter',
  model: 'model',
} as const;

/** Resolved output artifact details returned by the server. */
export interface OutputResponse {
  name: string;
  /** Output artifact type: `model` (full weights) or `adapter` (LoRA weights). */
  type: OutputNameType;
  /** FileSet name where output artifacts are stored. */
  fileset: string;
  description?: string;
}

/** Weights & Biases integration configuration. */
export interface WandBParams {
  project?: string;
  name?: string;
  entity?: string;
  tags?: string[];
  notes?: string;
  base_url?: string;
  api_key_secret?: SecretRef;
}

export type MLflowParamsTags = { [key: string]: string };

/** MLflow integration configuration. */
export interface MLflowParams {
  experiment_name?: string;
  name?: string;
  tags?: MLflowParamsTags;
  description?: string;
  tracking_uri?: string;
}

/** Third-party integration configurations shared by both backends. */
export interface IntegrationsSpec {
  wandb?: WandBParams;
  mlflow?: MLflowParams;
}

// ----- Unsloth-only deployment config -----

export type DeploymentParamsAdditionalEnvs = { [key: string]: string };

/** Tool calling configuration for NIM deployments. */
export interface ToolCallParams {
  tool_call_parser?: string;
  tool_call_plugin?: string;
  auto_tool_choice?: boolean;
}

/** Inline NIM deployment parameters (unsloth `deployment_config`). */
export interface DeploymentParams {
  gpu?: number;
  additional_envs?: DeploymentParamsAdditionalEnvs;
  disk_size?: string;
  image_name?: string;
  image_tag?: string;
  lora_enabled?: boolean;
  tool_call_config?: ToolCallParams;
}

// ===================================================================================
// Automodel backend (SFT + distillation, distributed training via `parallelism`)
// ===================================================================================

export type AutomodelTrainingType = 'sft' | 'distillation';
export type AutomodelFinetuningType = 'lora' | 'all_weights' | 'lora_merged';
export type TeacherPrecision = 'bf16' | 'fp16' | 'fp32';

/** LoRA adapter configuration (automodel). */
export interface AutomodelLoRAParams {
  rank: number;
  alpha: number;
  dropout: number;
  merge: boolean;
  target_modules?: string[];
}

export interface AutomodelDatasetSpec {
  /** Training fileset as 'name' or 'workspace/name'. */
  training: string;
  validation?: string;
  prompt_template?: string;
}

export interface AutomodelTrainingSpec {
  training_type: AutomodelTrainingType;
  finetuning_type: AutomodelFinetuningType;
  lora?: AutomodelLoRAParams;
  max_seq_length: number;
  /** Model precision for training. Auto-detected from the checkpoint when unset. */
  precision?: Precision;
  execution_profile?: string;
  // Distillation-only fields (present with defaults on canonical output; optional for read tolerance).
  teacher_model?: string;
  distillation_ratio?: number;
  distillation_temperature?: number;
  teacher_precision?: TeacherPrecision;
  offload_teacher?: boolean;
}

export interface AutomodelScheduleSpec {
  epochs: number;
  max_steps?: number;
  val_check_interval?: number;
  seed?: number;
}

export interface AutomodelBatchSpec {
  global_batch_size: number;
  micro_batch_size: number;
  sequence_packing: boolean;
}

export interface AutomodelOptimizerSpec {
  learning_rate: number;
  min_learning_rate?: number;
  weight_decay: number;
  adam_beta1: number;
  adam_beta2: number;
  warmup_steps: number;
}

/** Distributed training parallelism configuration (automodel). */
export interface ParallelismSpec {
  num_nodes: number;
  num_gpus_per_node: number;
  tensor_parallel_size: number;
  pipeline_parallel_size: number;
  context_parallel_size: number;
  expert_parallel_size?: number;
  sequence_parallel: boolean;
}

/** Canonical automodel job spec returned by the server. */
export interface AutomodelJobSpec {
  name?: string;
  model: string;
  dataset: AutomodelDatasetSpec;
  training: AutomodelTrainingSpec;
  schedule: AutomodelScheduleSpec;
  batch: AutomodelBatchSpec;
  optimizer: AutomodelOptimizerSpec;
  parallelism: ParallelismSpec;
  output: OutputResponse;
  integrations?: IntegrationsSpec;
}

// ===================================================================================
// Unsloth backend (SFT only, single-GPU, optional deployment)
// ===================================================================================

export type UnslothFinetuningType = 'lora' | 'all_weights';
export type UnslothModelDtype = 'auto' | 'bfloat16' | 'float16' | 'float32';
export type UnslothLoRABias = 'none' | 'all' | 'lora_only';
export type UnslothGradientCheckpointing = 'unsloth' | 'true' | 'false';
export type UnslothOptim =
  | 'adamw_torch'
  | 'adamw_torch_fused'
  | 'adamw_8bit'
  | 'paged_adamw_8bit'
  | 'sgd';
export type UnslothLrScheduler =
  | 'linear'
  | 'cosine'
  | 'constant'
  | 'constant_with_warmup'
  | 'cosine_with_restarts';
export type UnslothSaveMethod = 'lora' | 'merged_16bit' | 'merged_4bit';
export type UnslothHardwarePrecision = 'bf16' | 'fp16';

export type ModelLoadSpecDeviceMap = string | number | { [key: string]: number };

export interface ModelLoadSpec {
  /** Base model as 'name' or 'workspace/name'. */
  name: string;
  max_seq_length: number;
  load_in_4bit: boolean;
  load_in_8bit: boolean;
  dtype: UnslothModelDtype;
  trust_remote_code: boolean;
  device_map?: ModelLoadSpecDeviceMap;
}

/** LoRA adapter configuration (unsloth). */
export interface UnslothLoRAParams {
  rank: number;
  alpha: number;
  dropout: number;
  target_modules: string[];
  bias: UnslothLoRABias;
  use_rslora: boolean;
  random_state: number;
}

export interface UnslothDatasetSpec {
  /** Training fileset as 'name' or 'workspace/name'. */
  path: string;
  text_field: string;
  apply_chat_template: boolean;
  validation_path?: string;
  packing: boolean;
}

export interface UnslothTrainingSpec {
  training_type: 'sft';
  finetuning_type: UnslothFinetuningType;
  lora?: UnslothLoRAParams;
  use_gradient_checkpointing: UnslothGradientCheckpointing;
}

export interface UnslothScheduleSpec {
  epochs: number;
  max_steps?: number;
  warmup_steps: number;
  warmup_ratio?: number;
  lr_scheduler_type: UnslothLrScheduler;
  logging_steps: number;
  save_steps?: number;
  eval_steps?: number;
  seed: number;
}

export interface UnslothBatchSpec {
  per_device_train_batch_size: number;
  gradient_accumulation_steps: number;
}

export interface UnslothOptimizerSpec {
  learning_rate: number;
  weight_decay: number;
  optim: UnslothOptim;
}

/** Single-node hardware configuration (unsloth). */
export interface HardwareSpec {
  /** Comma-separated GPU indices (e.g. '0' or '0,1'). */
  gpus?: string;
  precision: UnslothHardwarePrecision;
}

/** Unsloth output artifact details (adds the save method used). */
export interface UnslothOutputResponse extends OutputResponse {
  save_method: UnslothSaveMethod;
}

/** Canonical unsloth job spec returned by the server. */
export interface UnslothJobSpec {
  name?: string;
  model: ModelLoadSpec;
  dataset: UnslothDatasetSpec;
  training: UnslothTrainingSpec;
  schedule: UnslothScheduleSpec;
  batch: UnslothBatchSpec;
  optimizer: UnslothOptimizerSpec;
  hardware: HardwareSpec;
  integrations?: IntegrationsSpec;
  output: UnslothOutputResponse;
  deployment_config?: string | DeploymentParams;
}

// ===================================================================================
// Job envelope + discriminated union
// ===================================================================================

export type CustomizationJobSpec = AutomodelJobSpec | UnslothJobSpec;

export type CustomizationJobStatusDetails = { [key: string]: unknown };
export type CustomizationJobErrorDetails = { [key: string]: unknown };
export type CustomizationJobOwnership = { [key: string]: unknown };
export type CustomizationJobCustomFields = { [key: string]: unknown };

/** Generic job envelope (mirrors the platform job response, spec typed per backend). */
export interface BaseJob<TSpec extends CustomizationJobSpec> {
  id?: string;
  name: string;
  description?: string;
  project?: string;
  workspace?: string;
  created_at?: string;
  updated_at?: string;
  spec: TSpec;
  status?: PlatformJobStatus;
  status_details?: CustomizationJobStatusDetails;
  error_details?: CustomizationJobErrorDetails;
  ownership?: CustomizationJobOwnership;
  custom_fields?: CustomizationJobCustomFields;
}

export type AutomodelJob = BaseJob<AutomodelJobSpec>;
export type UnslothJob = BaseJob<UnslothJobSpec>;
export type CustomizationJob = AutomodelJob | UnslothJob;

// ----- Backend discriminators -----
// Operate on the untyped `spec` returned by the generic platform jobs API and narrow it.

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

/** True when the spec was produced by the automodel backend (carries `parallelism`). */
export const isAutomodelSpec = (spec: unknown): spec is AutomodelJobSpec =>
  isObject(spec) && 'parallelism' in spec;

/** True when the spec was produced by the unsloth backend (carries `hardware`). */
export const isUnslothSpec = (spec: unknown): spec is UnslothJobSpec =>
  isObject(spec) && 'hardware' in spec;

/** Derive the training backend from a job spec, or `undefined` if it isn't a customization spec. */
export const getCustomizationBackend = (spec: unknown): CustomizationBackend | undefined => {
  if (isAutomodelSpec(spec)) return CustomizationBackend.automodel;
  if (isUnslothSpec(spec)) return CustomizationBackend.unsloth;
  return undefined;
};

export const isAutomodelJob = (job: CustomizationJob): job is AutomodelJob =>
  isAutomodelSpec(job.spec);

export const isUnslothJob = (job: CustomizationJob): job is UnslothJob => isUnslothSpec(job.spec);
