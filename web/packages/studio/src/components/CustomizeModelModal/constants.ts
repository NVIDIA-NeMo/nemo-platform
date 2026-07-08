// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Fine-tuning is now run through the Code Agent (guided); prompt-tuning uses the in-app form.
export type CustomizationMethod = 'fine-tuned' | 'prompt-tuned';

export interface CustomizationMethodOption {
  value: CustomizationMethod;
  title: string;
  tags: string[];
  tagColor: 'purple' | 'teal';
  description: string;
  bestFor: string;
}

export const CUSTOMIZATION_METHODS: CustomizationMethodOption[] = [
  {
    value: 'fine-tuned',
    title: 'Fine-Tuned',
    tags: ['SFT', 'LoRA'],
    tagColor: 'purple',
    description:
      'Highest accuracy. Opens the Code Agent to guide you through configuring and launching a fine-tuning job.',
    bestFor: 'Domain adaptation, strict output control, or minimizing error rates.',
  },
  {
    value: 'prompt-tuned',
    title: 'Prompt Tuned',
    tags: ['ICLs'],
    tagColor: 'teal',
    description: 'Fastest to start. Requires only prompts or a few examples.',
    bestFor: 'Rapid iteration, prototyping, or when labeled data is limited.',
  },
];
