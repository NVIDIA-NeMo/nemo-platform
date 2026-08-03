// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import YAML from 'yaml';

/**
 * Loads a sample agent's config from a public static asset and injects the
 * selected model. Parse-then-set: the fetched YAML's model literal is
 * overwritten, so the asset can stay byte-identical to the plugin's
 * ${NEMO_DEFAULT_MODEL} version (the platform service doesn't resolve that).
 *
 * Branches on the config's own `config_format`:
 * - NAT (`nat-workflow-v1`, the default when absent): model lives at
 *   `llms.llm.model_name`.
 * - Fabric (`nemo-agents-spec-v1`): model lives at `models.default.model`; the
 *   selected harness inherits it when it declares no model of its own.
 */
export const loadSampleAgentConfig = async (
  agentConfigPath: string,
  modelName: string
): Promise<Record<string, unknown>> => {
  const text = await fetchSampleText(agentConfigPath);
  const config = YAML.parse(text) as Record<string, unknown>;

  if (config?.config_format === 'nemo-agents-spec-v1') {
    injectFabricModel(config, modelName, agentConfigPath);
    return config;
  }

  injectNatModel(config, modelName, agentConfigPath);
  return config;
};

/** NAT workflow config: overwrite `llms.llm.model_name`. */
const injectNatModel = (
  config: Record<string, unknown>,
  modelName: string,
  agentConfigPath: string
): void => {
  const llm = (config?.llms as { llm?: unknown } | undefined)?.llm;
  if (!llm || typeof llm !== 'object' || Array.isArray(llm)) {
    throw new Error(`Sample agent config ${agentConfigPath} is missing llms.llm`);
  }
  (llm as Record<string, unknown>).model_name = modelName;
};

/** Fabric (nemo-agents-spec-v1) config: overwrite `models.default.model`. */
const injectFabricModel = (
  config: Record<string, unknown>,
  modelName: string,
  agentConfigPath: string
): void => {
  const models = config?.models as { default?: unknown } | undefined;
  const defaultModel = models?.default;
  if (!defaultModel || typeof defaultModel !== 'object' || Array.isArray(defaultModel)) {
    throw new Error(`Sample agent config ${agentConfigPath} is missing models.default`);
  }
  (defaultModel as Record<string, unknown>).model = modelName;
};
