// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TemplateBadge } from '@studio/components/CreateCustomizationStart/types';
import { CustomizationBackend } from '@studio/util/customizationBackend';
import type { CustomizationFormFields } from '@studio/util/forms/customization';

/**
 * Backend badge. RL is coloured because it is the one that changes what the job *is*
 * rather than how it runs — the two supervised backends read as interchangeable and are
 * deliberately left neutral so RL stands out in a mixed list.
 */
const BACKEND_BADGE: Record<CustomizationBackend, TemplateBadge> = {
  [CustomizationBackend.automodel]: { label: 'Automodel', color: 'gray' },
  [CustomizationBackend.unsloth]: { label: 'Unsloth', color: 'gray' },
  [CustomizationBackend.rl]: { label: 'RL', color: 'purple' },
};

/** Training-method badge, keyed by the label each backend's form settles on. */
const METHOD_COLOR: Record<string, TemplateBadge['color']> = {
  LoRA: 'blue',
  Full: 'gray',
  DPO: 'yellow',
  GRPO: 'green',
};

const methodBadge = (label: string): TemplateBadge => ({
  label,
  color: METHOD_COLOR[label] ?? 'gray',
});

/**
 * The training method a saved template will run.
 *
 * RL splits on `grpo.trainingType` rather than `rl.training.type`: the form holds one
 * `rl.training` object and uses the former as the discriminator, so it is the field that
 * is actually correct on a half-configured template.
 */
export const trainingLabelForFields = (fields: CustomizationFormFields): string => {
  if (fields.backend === CustomizationBackend.rl) {
    return fields.grpo.trainingType === 'grpo' ? 'GRPO' : 'DPO';
  }
  const finetuningType =
    fields.backend === CustomizationBackend.automodel
      ? fields.automodel.training.finetuning_type
      : fields.unsloth.training?.finetuning_type;
  return finetuningType === 'lora' || finetuningType === 'lora_merged' ? 'LoRA' : 'Full';
};

export const templateBadges = (
  backend: CustomizationBackend,
  trainingLabel: string
): TemplateBadge[] => [BACKEND_BADGE[backend], methodBadge(trainingLabel)];

/**
 * The model and dataset a saved template will train on, as footer lines.
 *
 * Mirrors `MODEL_FIELD_BY_BACKEND` / `DATASET_FIELD_BY_BACKEND` — those hold the form
 * *paths* for react-hook-form, which cannot be used to read a plain object, so the same
 * per-backend shape is restated here. RL's dataset is a bare string; the other two nest it.
 *
 * References are workspace-qualified (`default/qwen3-0-6b`); the prefix is dropped because
 * a template can only reference entities in the workspace already being viewed.
 */
export const templateFooterLines = (fields: CustomizationFormFields): string[] => {
  const shortRef = (ref: string | undefined) => ref?.split('/').pop() ?? '';

  let model: string | undefined;
  let dataset: string | undefined;
  if (fields.backend === CustomizationBackend.automodel) {
    model = fields.automodel.model;
    dataset = fields.automodel.dataset?.training;
  } else if (fields.backend === CustomizationBackend.unsloth) {
    model = fields.unsloth.model?.name;
    dataset = fields.unsloth.dataset?.path;
  } else {
    model = fields.rl.model;
    dataset = fields.rl.dataset;
  }

  // Dot-separated on one line, matching the shipped recipes' stats footer.
  return [[shortRef(model) || '—', shortRef(dataset) || '—'].join(' · ')];
};
