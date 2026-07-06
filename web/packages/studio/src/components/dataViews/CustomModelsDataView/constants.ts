// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FinetuningType } from '@nemo/sdk/generated/platform/schema';

export const FINETUNING_TYPE_OPTIONS = [
  { value: FinetuningType.lora, children: 'LoRA' },
  { value: FinetuningType.lora_merged, children: 'LoRA Merged' },
  { value: FinetuningType.all_weights, children: 'All Weights' },
  { value: FinetuningType.last_layer, children: 'Last Layer' },
  { value: FinetuningType.top_layers, children: 'Top Layers' },
  { value: FinetuningType.gradual_unfreezing, children: 'Gradual Unfreezing' },
  { value: FinetuningType.bias_only, children: 'Bias Only' },
  { value: FinetuningType.attention_only, children: 'Attention Only' },
  { value: FinetuningType.qlora, children: 'QLoRA' },
  { value: FinetuningType.adalora, children: 'AdaLoRA' },
  { value: FinetuningType.dora, children: 'DoRA' },
  { value: FinetuningType.lora_plus, children: 'LoRA+' },
  { value: FinetuningType.prompt_tuning, children: 'Prompt Tuning' },
  { value: FinetuningType.prefix_tuning, children: 'Prefix Tuning' },
  { value: FinetuningType.p_tuning, children: 'P-Tuning' },
  { value: FinetuningType.p_tuning_v2, children: 'P-Tuning v2' },
  { value: FinetuningType.soft_prompt, children: 'Soft Prompt' },
  { value: FinetuningType.ppo, children: 'PPO' },
  { value: FinetuningType.dpo, children: 'DPO' },
  { value: FinetuningType.cdpo, children: 'cDPO' },
  { value: FinetuningType.ipo, children: 'IPO' },
  { value: FinetuningType.orpo, children: 'ORPO' },
  { value: FinetuningType.kto, children: 'KTO' },
  { value: FinetuningType.rrhf, children: 'RRHF' },
  { value: FinetuningType.grpo, children: 'GRPO' },
];

/** Column filter options in FilterItem format ({ value, label }) for single-select filters. */
export const FINETUNING_TYPE_FILTER_OPTIONS = FINETUNING_TYPE_OPTIONS.map((opt) => ({
  value: opt.value,
  label: opt.children,
}));
