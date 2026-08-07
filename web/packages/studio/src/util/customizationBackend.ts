// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import type {
  AutomodelJobOutput,
  AutomodelJobsJob,
  RlJobOutput,
  RlJobsJob,
  RlParallelismParams,
  UnslothJobOutput,
  UnslothJobsJob,
} from '@nemo/sdk/generated/customizer/schema';

export const CustomizationBackend = {
  automodel: 'automodel',
  unsloth: 'unsloth',
  rl: 'rl',
} as const;
export type CustomizationBackend = (typeof CustomizationBackend)[keyof typeof CustomizationBackend];

/**
 * Frontend-only stub for the planned GRPO training schema.
 * Mirrors the backend's intended GRPOTraining shape before the API schema lands.
 * Remove and replace with generated types once nemo-rl-plugin ships GRPOTraining.
 */
export interface GrpoTraining {
  type: 'grpo';
  epochs?: number;
  learning_rate?: number;
  batch_size?: number;
  micro_batch_size?: number;
  max_seq_length?: number;
  warmup_steps?: number;
  weight_decay?: number;
  num_generations?: number;
  epsilon?: number;
  kl_coeff?: number;
  reward_model?: string;
  parallelism?: RlParallelismParams;
}

export interface GrpoJobSpec {
  model: string;
  dataset: string;
  training: GrpoTraining;
  output: { name?: string };
}

export interface GrpoJob {
  id?: string;
  name: string;
  description?: string;
  workspace?: string;
  created_at?: string;
  updated_at?: string;
  spec: GrpoJobSpec;
  status?: PlatformJobStatus;
  status_details?: Record<string, unknown>;
  error_details?: unknown;
  ownership?: { created_by?: string };
}

export type CustomizationJobSpec = AutomodelJobOutput | UnslothJobOutput | RlJobOutput | GrpoJobSpec;
export type AutomodelJob = AutomodelJobsJob;
export type UnslothJob = UnslothJobsJob;
export type RlJob = RlJobsJob;
export type CustomizationJob = AutomodelJobsJob | UnslothJobsJob | RlJobsJob | GrpoJob;
export type CustomizationJobStatusDetails = Record<string, unknown>;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

export const isAutomodelSpec = (spec: unknown): spec is AutomodelJobOutput =>
  isObject(spec) && 'parallelism' in spec;

export const isUnslothSpec = (spec: unknown): spec is UnslothJobOutput =>
  isObject(spec) && 'hardware' in spec;

const hasTrainingType = (spec: unknown, type: string): boolean =>
  isObject(spec) &&
  !('parallelism' in spec) &&
  !('hardware' in spec) &&
  'training' in spec &&
  isObject((spec as { training: unknown }).training) &&
  (spec as { training: { type?: string } }).training.type === type;

export const isRlSpec = (spec: unknown): spec is RlJobOutput => hasTrainingType(spec, 'dpo');

export const isGrpoSpec = (spec: unknown): spec is GrpoJobSpec => hasTrainingType(spec, 'grpo');

export const getCustomizationBackend = (spec: unknown): CustomizationBackend | undefined => {
  if (isAutomodelSpec(spec)) return CustomizationBackend.automodel;
  if (isUnslothSpec(spec)) return CustomizationBackend.unsloth;
  if (isRlSpec(spec) || isGrpoSpec(spec)) return CustomizationBackend.rl;
  return undefined;
};

export const isAutomodelJob = (job: CustomizationJob): job is AutomodelJob =>
  isAutomodelSpec(job.spec);

export const isUnslothJob = (job: CustomizationJob): job is UnslothJob => isUnslothSpec(job.spec);

export const isRlJob = (job: CustomizationJob): job is RlJob => isRlSpec(job.spec);

export const isGrpoJob = (job: CustomizationJob): job is GrpoJob => isGrpoSpec(job.spec);
