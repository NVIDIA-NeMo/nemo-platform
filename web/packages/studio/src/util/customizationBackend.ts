// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  AutomodelJobOutput,
  AutomodelJobsJob,
  RlJobOutput,
  RlJobsJob,
  UnslothJobOutput,
  UnslothJobsJob,
} from '@nemo/sdk/generated/customizer/schema';

export const CustomizationBackend = {
  automodel: 'automodel',
  unsloth: 'unsloth',
  rl: 'rl',
} as const;
export type CustomizationBackend = (typeof CustomizationBackend)[keyof typeof CustomizationBackend];

export type CustomizationJobSpec = AutomodelJobOutput | UnslothJobOutput | RlJobOutput;
export type AutomodelJob = AutomodelJobsJob;
export type UnslothJob = UnslothJobsJob;
export type RlJob = RlJobsJob;
export type CustomizationJob = AutomodelJobsJob | UnslothJobsJob | RlJobsJob;
export type CustomizationJobStatusDetails = Record<string, unknown>;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

export const isAutomodelSpec = (spec: unknown): spec is AutomodelJobOutput =>
  isObject(spec) && 'parallelism' in spec;

export const isUnslothSpec = (spec: unknown): spec is UnslothJobOutput =>
  isObject(spec) && 'hardware' in spec;

export const isRlSpec = (spec: unknown): spec is RlJobOutput =>
  isObject(spec) &&
  !('parallelism' in spec) &&
  !('hardware' in spec) &&
  'training' in spec &&
  isObject((spec as { training: unknown }).training) &&
  (spec as { training: { type?: string } }).training.type === 'dpo';

export const getCustomizationBackend = (spec: unknown): CustomizationBackend | undefined => {
  if (isAutomodelSpec(spec)) return CustomizationBackend.automodel;
  if (isUnslothSpec(spec)) return CustomizationBackend.unsloth;
  if (isRlSpec(spec)) return CustomizationBackend.rl;
  return undefined;
};

export const isAutomodelJob = (job: CustomizationJob): job is AutomodelJob =>
  isAutomodelSpec(job.spec);

export const isUnslothJob = (job: CustomizationJob): job is UnslothJob => isUnslothSpec(job.spec);

export const isRlJob = (job: CustomizationJob): job is RlJob => isRlSpec(job.spec);
