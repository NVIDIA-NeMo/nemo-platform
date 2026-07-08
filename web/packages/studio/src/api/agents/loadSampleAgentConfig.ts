// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import YAML from 'yaml';

/**
 * Loads a sample agent's NAT workflow config from a public static asset and
 * injects the selected model. Parse-then-set: the fetched YAML's model_name
 * literal is overwritten, so the asset can stay byte-identical to the plugin's
 * ${NEMO_DEFAULT_MODEL} version (the platform service doesn't resolve that).
 */
export const loadSampleAgentConfig = async (
  agentConfigPath: string,
  modelName: string
): Promise<Record<string, unknown>> => {
  const text = await fetchSampleText(agentConfigPath);
  const config = YAML.parse(text) as Record<string, unknown>;
  const llm = (config?.llms as { llm?: unknown } | undefined)?.llm;
  if (!llm || typeof llm !== 'object' || Array.isArray(llm)) {
    throw new Error(`Sample agent config ${agentConfigPath} is missing llms.llm`);
  }
  (llm as Record<string, unknown>).model_name = modelName;
  return config;
};
