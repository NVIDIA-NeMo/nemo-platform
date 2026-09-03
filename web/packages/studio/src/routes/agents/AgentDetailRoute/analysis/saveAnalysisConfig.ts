// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  insightsDisableAnalysisConfig,
  insightsEnableAnalysisConfig,
  type AnalysisConfig,
} from '@studio/api/optimizer';

export interface AnalysisConfigDraft {
  enabled: boolean;
  defaultModel: string;
  fastModel: string;
}

/**
 * Persist an edited analysis config over an API that cannot express the edit directly.
 *
 * The service offers `enable` (sets both models and forces `enabled: true`), `disable` (clears the
 * flag alone), and a `PATCH` that carries only `enabled`. Nothing sets models while leaving the
 * flag alone, so "disabled, with these models" has to be written as enable-then-disable — which
 * means a save can leave the config briefly enabled before the second call lands.
 */
export const saveAnalysisConfig = async (
  workspace: string,
  agent: string,
  draft: AnalysisConfigDraft,
  stored: AnalysisConfig | undefined
): Promise<AnalysisConfig> => {
  const modelsChanged =
    draft.defaultModel !== stored?.default_model || draft.fastModel !== stored?.fast_model;

  // No config exists yet, so `enable` is the only call that can create one.
  const mustWriteModels = modelsChanged || !stored;

  if (!mustWriteModels) {
    if (draft.enabled === stored.enabled) return stored;
    return draft.enabled
      ? insightsEnableAnalysisConfig(workspace, agent, {
          default_model: stored.default_model,
          fast_model: stored.fast_model,
        })
      : insightsDisableAnalysisConfig(workspace, agent);
  }

  const enabled = await insightsEnableAnalysisConfig(workspace, agent, {
    default_model: draft.defaultModel,
    fast_model: draft.fastModel,
  });

  return draft.enabled ? enabled : insightsDisableAnalysisConfig(workspace, agent);
};
