// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';

/**
 * Model names an agent is configured to call, across both config formats: NAT
 * workflows name them under `llms`, `nemo-agents-spec-v1` under `models` and on
 * each harness.
 */
export const getAgentModelNames = (config: AgentConfig | undefined): string[] => {
  const seen = new Set<string>();
  for (const llm of Object.values(config?.llms ?? {})) {
    if (llm.model_name) seen.add(llm.model_name);
  }
  for (const model of Object.values(config?.models ?? {})) {
    if (model?.model) seen.add(model.model);
  }
  for (const harness of Object.values(config?.harnesses ?? {})) {
    if (harness?.model?.model) seen.add(harness.model.model);
  }
  return [...seen];
};
