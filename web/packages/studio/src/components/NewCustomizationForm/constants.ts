// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { OptimizerType } from '@nemo/sdk/generated/customizer/schema';

/** Optimizer + LR-scheduler pairs offered by the RL backends (DPO and GRPO share the set). */
export const OPTIMIZER_TYPE_ITEMS = [
  { value: OptimizerType.adamw_with_cosine_annealing, children: 'AdamW + Cosine Annealing' },
  { value: OptimizerType.adam_with_cosine_annealing, children: 'Adam + Cosine Annealing' },
  { value: OptimizerType.adamw_with_flat_lr, children: 'AdamW + Flat LR' },
  { value: OptimizerType.adam_with_flat_lr, children: 'Adam + Flat LR' },
];
