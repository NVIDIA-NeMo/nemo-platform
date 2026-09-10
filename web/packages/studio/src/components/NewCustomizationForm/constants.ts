// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  AutomodelTrainingSpecTeacherPrecision,
  OptimizerType,
  UnslothHardwareSpecPrecision,
  UnslothOptimizerSpecOptim,
  UnslothScheduleSpecLrSchedulerType,
  UnslothTrainingSpecUseGradientCheckpointing,
} from '@nemo/sdk/generated/customizer/schema';

/** Optimizer + LR-scheduler pairs the RL backend accepts. */
export const OPTIMIZER_TYPE_ITEMS = [
  { value: OptimizerType.adamw_with_cosine_annealing, children: 'AdamW + Cosine Annealing' },
  { value: OptimizerType.adam_with_cosine_annealing, children: 'Adam + Cosine Annealing' },
  { value: OptimizerType.adamw_with_flat_lr, children: 'AdamW + Flat LR' },
  { value: OptimizerType.adam_with_flat_lr, children: 'Adam + Flat LR' },
];

/** `bf16 | fp16 | fp32` — the teacher's precision during distillation. */
export const TEACHER_PRECISION_ITEMS = [
  { value: AutomodelTrainingSpecTeacherPrecision.bf16, children: 'bf16' },
  { value: AutomodelTrainingSpecTeacherPrecision.fp16, children: 'fp16' },
  { value: AutomodelTrainingSpecTeacherPrecision.fp32, children: 'fp32' },
];

/** Unsloth LR schedulers. */
export const UNSLOTH_LR_SCHEDULER_ITEMS = [
  { value: UnslothScheduleSpecLrSchedulerType.linear, children: 'Linear' },
  { value: UnslothScheduleSpecLrSchedulerType.cosine, children: 'Cosine' },
  { value: UnslothScheduleSpecLrSchedulerType.constant, children: 'Constant' },
  { value: UnslothScheduleSpecLrSchedulerType.constant_with_warmup, children: 'Constant + Warmup' },
  { value: UnslothScheduleSpecLrSchedulerType.cosine_with_restarts, children: 'Cosine + Restarts' },
];

/** Unsloth optimizers. The 8-bit and paged variants are the VRAM-saving ones. */
export const UNSLOTH_OPTIM_ITEMS = [
  { value: UnslothOptimizerSpecOptim.adamw_8bit, children: 'AdamW 8-bit' },
  { value: UnslothOptimizerSpecOptim.paged_adamw_8bit, children: 'Paged AdamW 8-bit' },
  { value: UnslothOptimizerSpecOptim.adamw_torch, children: 'AdamW (Torch)' },
  { value: UnslothOptimizerSpecOptim.adamw_torch_fused, children: 'AdamW (Torch, fused)' },
  { value: UnslothOptimizerSpecOptim.sgd, children: 'SGD' },
];

/** Unsloth compute precision. */
export const UNSLOTH_PRECISION_ITEMS = [
  { value: UnslothHardwareSpecPrecision.bf16, children: 'bf16' },
  { value: UnslothHardwareSpecPrecision.fp16, children: 'fp16' },
];

/** Unsloth's own kernel, or plain on/off. */
export const UNSLOTH_GRADIENT_CHECKPOINTING_ITEMS = [
  { value: UnslothTrainingSpecUseGradientCheckpointing.unsloth, children: 'Unsloth kernel' },
  { value: UnslothTrainingSpecUseGradientCheckpointing.true, children: 'Enabled' },
  { value: UnslothTrainingSpecUseGradientCheckpointing.false, children: 'Disabled' },
];

/** Automodel compute precision. */
export const AUTOMODEL_PRECISION_ITEMS = [
  { value: 'bf16', children: 'bf16' },
  { value: 'fp16', children: 'fp16' },
  { value: 'fp32', children: 'fp32' },
  { value: 'fp8', children: 'fp8' },
];

/** Automodel training recipe. `auto` lets the backend pick from the model architecture. */
export const AUTOMODEL_RECIPE_ITEMS = [
  { value: 'auto', children: 'Auto' },
  { value: 'sft', children: 'SFT' },
  { value: 'bi_encoder', children: 'Bi-encoder' },
  { value: 'cross_encoder', children: 'Cross-encoder' },
];
