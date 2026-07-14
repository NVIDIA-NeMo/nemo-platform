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
  /** Module name patterns to exclude from LoRA (e.g. ['*.out_proj']). */
  exclude_modules?: string[];
  /** Use the optimized Triton LoRA kernel. Backend defaults to true. */
  use_triton?: boolean;
}

export type AutomodelAttnImplementation = 'sdpa' | 'flash_attention_2' | 'eager';
export type AutomodelOptimizerAlgo = 'Adam' | 'AdamW';
export type AutomodelLrDecayStyle = 'cosine' | 'linear' | 'constant';

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
  /** Attention kernel implementation. Backend defaults to 'sdpa'. */
  attn_implementation?: AutomodelAttnImplementation;
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
  /** Max samples sampled to estimate packing. Backend defaults to 1000. */
  sequence_packing_max_samples?: number;
}

export interface AutomodelOptimizerSpec {
  learning_rate: number;
  min_learning_rate?: number;
  weight_decay: number;
  adam_beta1: number;
  adam_beta2: number;
  warmup_steps: number;
  /** Adam/AdamW epsilon. Backend defaults to 1e-8. */
  adam_eps?: number;
  /** Optimizer algorithm. Backend defaults to 'Adam'. */
  optimizer?: AutomodelOptimizerAlgo;
  /** Learning-rate decay schedule. Backend defaults to 'cosine'. */
  lr_decay_style?: AutomodelLrDecayStyle;
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
  /** RoPE scaling config passed through to the HF model loader. */
  rope_scaling?: { [key: string]: unknown } | null;
}

/** LoRA weight-initialization scheme (unsloth/PEFT). `true` = PEFT default. */
export type UnslothInitLoraWeights = boolean | 'gaussian' | 'pissa' | 'olora' | 'loftq';

/** LoRA adapter configuration (unsloth). */
export interface UnslothLoRAParams {
  rank: number;
  alpha: number;
  dropout: number;
  target_modules: string[];
  bias: UnslothLoRABias;
  use_rslora: boolean;
  random_state: number;
  /** Use DoRA (weight-decomposed LoRA). Backend defaults to false. */
  use_dora?: boolean;
  /** LoftQ quantization config for LoRA init. */
  loftq_config?: { [key: string]: unknown } | null;
  /** Extra modules to train and save fully (beyond the adapter). */
  modules_to_save?: string[] | null;
  /** Restrict LoRA to specific transformer layer indices. */
  layers_to_transform?: number | number[] | null;
  /** Layer-replication ranges for depth up-scaling. */
  layer_replication?: number[][] | null;
  /** LoRA weight init scheme. Backend defaults to true (PEFT default). */
  init_lora_weights?: UnslothInitLoraWeights;
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
  /** Extra kwargs forwarded to the LR scheduler. */
  lr_scheduler_kwargs?: { [key: string]: unknown } | null;
}

export interface UnslothBatchSpec {
  per_device_train_batch_size: number;
  gradient_accumulation_steps: number;
}

export interface UnslothOptimizerSpec {
  learning_rate: number;
  weight_decay: number;
  optim: UnslothOptim;
  /** Adam/AdamW beta1. Backend defaults to 0.9. */
  adam_beta1?: number;
  /** Adam/AdamW beta2. Backend defaults to 0.999. */
  adam_beta2?: number;
  /** Adam/AdamW epsilon. Backend defaults to 1e-8. */
  adam_epsilon?: number;
  /** Gradient-clipping max norm. Backend defaults to 1.0. */
  max_grad_norm?: number;
  /** Label smoothing for cross-entropy. Backend defaults to 0.0 (disabled). */
  label_smoothing_factor?: number;
  /** NEFTune embedding-noise alpha. null disables. */
  neftune_noise_alpha?: number | null;
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
// Create-request input types (not yet generated; inlined alongside the response types)
// ===================================================================================

/** Output artifact request used in create-job bodies. */
export interface OutputRequest {
  name?: string;
  description?: string;
}

/** Automodel create-job request body (wrapped in the platform job envelope). */
export interface AutomodelJobInput {
  name?: string;
  description?: string;
  spec: {
    model: string;
    dataset: AutomodelDatasetSpec;
    training: Omit<AutomodelTrainingSpec, 'execution_profile'> & { execution_profile?: string };
    schedule?: Partial<AutomodelScheduleSpec>;
    batch?: Partial<AutomodelBatchSpec>;
    optimizer?: Partial<AutomodelOptimizerSpec>;
    parallelism?: Partial<ParallelismSpec>;
    // Automodel requires `name` whenever an output object is present.
    output?: OutputRequest & { name: string };
    integrations?: IntegrationsSpec;
  };
}

/** Unsloth create-job request body (wrapped in the platform job envelope). */
export interface UnslothJobInput {
  name?: string;
  description?: string;
  spec: {
    model: Omit<ModelLoadSpec, 'device_map'> & { device_map?: ModelLoadSpecDeviceMap };
    dataset: UnslothDatasetSpec;
    training?: Omit<UnslothTrainingSpec, 'training_type'> & { training_type?: 'sft' };
    schedule?: Partial<UnslothScheduleSpec>;
    batch?: Partial<UnslothBatchSpec>;
    optimizer?: Partial<UnslothOptimizerSpec>;
    hardware?: Partial<HardwareSpec>;
    output?: OutputRequest & { save_method?: UnslothSaveMethod };
    integrations?: IntegrationsSpec;
    deployment_config?: string | DeploymentParams;
  };
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
