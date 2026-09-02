// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useModelChatAvailability } from '@studio/hooks/useModelChatAvailability';
import { useModelLoraEnabled } from '@studio/hooks/useModelLoraEnabled';

/**
 * Whether a model can be fine-tuned: it needs a fileset holding the base weights.
 * All three customization backends require one at job-compile time and reject the
 * job with a 422 otherwise, so this is also what the base-model pickers filter on.
 */
export const canFineTuneModel = (model: ModelEntity | null | undefined): boolean =>
  Boolean(model?.fileset);

export interface ModelCustomizationEligibility {
  canFineTune: boolean;
  canPromptTune: boolean;
  canCustomize: boolean;
  isLoading: boolean;
}

/**
 * Whether the given model can be fine-tuned, prompt-tuned, or neither.
 *
 * - Fine-tuning requires `model.fileset` to be populated (the fileset holds
 *   the weights/config needed as the training starting point).
 * - Prompt-tuning requires the model to be chat-available AND its deployment
 *   config to have `lora_enabled=true`. The latter is answered server-side via
 *   {@link useModelLoraEnabled}, which uses the models list filter.
 *
 * The two underlying queries fire in parallel — no client-side waterfall.
 */
export const useModelCustomizationEligibility = (
  model: ModelEntity | undefined
): ModelCustomizationEligibility => {
  const canFineTune = canFineTuneModel(model);

  const { isChatAvailable, isLoading: isChatLoading } = useModelChatAvailability(model);
  const { isLoraEnabled, isLoading: isLoraLoading } = useModelLoraEnabled(model);

  const canPromptTune = isChatAvailable && isLoraEnabled;

  return {
    canFineTune,
    canPromptTune,
    canCustomize: canFineTune || canPromptTune,
    isLoading: isChatLoading || isLoraLoading,
  };
};
