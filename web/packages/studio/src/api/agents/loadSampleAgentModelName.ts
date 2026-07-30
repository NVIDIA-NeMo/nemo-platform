// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import YAML from 'yaml';

export const loadSampleAgentModelName = async (agentConfigPath: string): Promise<string | null> => {
  const text = await fetchSampleText(agentConfigPath);
  const config = YAML.parse(text) as Record<string, unknown> | undefined;
  const llm = (config?.llms as { llm?: unknown } | undefined)?.llm;
  if (!llm || typeof llm !== 'object' || Array.isArray(llm)) return null;

  const modelName = (llm as Record<string, unknown>).model_name;
  if (typeof modelName !== 'string' || modelName.includes('${')) return null;

  const bare = modelName.includes('/') ? (modelName.split('/').pop() ?? modelName) : modelName;
  return bare.trim() || null;
};
