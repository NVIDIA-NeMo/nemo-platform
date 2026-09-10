// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  AutomodelTrainingSpecTeacherPrecision,
  OptimizerType,
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
