// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CreateConfigFormData } from '@studio/hooks/evaluation/useCreateConfigurationForm';

type InferenceRequestTemplate = CreateConfigFormData['configData']['inferenceRequestTemplate'];

/**
 * Build the inference request template preview.
 *
 * Template preview requires at minimum a prompt to be set; returns null when
 * no prompt is present.
 */
export const buildTemplatePreview = (
  inferenceRequestTemplate: InferenceRequestTemplate,
  templateSelectorInputPrompt: string | undefined
) => {
  // Template preview requires at minimum a prompt to be set
  if (!templateSelectorInputPrompt?.trim()) {
    return null;
  }

  if (inferenceRequestTemplate) {
    return {
      messages: inferenceRequestTemplate.messages,
    };
  }

  return {
    messages: [{ role: 'user', content: templateSelectorInputPrompt }],
  };
};
