// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import { DEFAULT_BUILD_MODEL_NAME } from '@studio/constants/constants';
import { GraduationCap } from 'lucide-react';

/**
 * The ready-made recipes shown as cards in the secondary area when "Start from a
 * template" is selected. One recipe today; add entries here as more are authored —
 * the card grid and selection flow scale to any number without further changes.
 */
export const FILESET_TEMPLATES: FilesetTemplate[] = [
  {
    id: 'sft-instruction',
    title: 'Instruction fine-tuning (SFT)',
    description:
      'Instruction–response pairs for supervised fine-tuning: a sampled topic, an LLM-generated user instruction, and a model answer.',
    icon: GraduationCap,
    tag: { label: 'Fine-tuning', color: 'blue', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values:
            'science, technology, history, arts, business, health, education, sports, travel, cooking',
        },
      },
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: {
          prompt:
            'Write a single, self-contained user instruction about {{ domain }}. Return only the instruction.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'response',
        values: {
          prompt:
            'Respond helpfully and concisely to the following instruction:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
];

export const findTemplate = (id: string): FilesetTemplate | undefined =>
  FILESET_TEMPLATES.find((template) => template.id === id);
