// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { fetchSampleText } from '@studio/api/agents/fetchSampleText';
import YAML from 'yaml';

/** Strip an interpolated or provider-qualified value down to the bare model name the workspace
 *  model list uses. Returns null for anything templated, since `${VAR}` names no model. */
const bareModelName = (value: unknown): string | null => {
  if (typeof value !== 'string' || value.includes('${')) return null;
  const bare = value.includes('/') ? (value.split('/').pop() ?? value) : value;
  return bare.trim() || null;
};

const asObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

/** The model a sample agent's config names, so the create modal can preselect it.
 *
 *  Mirrors the two shapes ``loadSampleAgentConfig`` writes back to:
 *  - NAT (`nat-workflow-v1`): `llms.llm.model_name`
 *  - Fabric (`nemo-agents-spec-v1`): `models.default.model`
 *
 *  Null when the config names no usable model; the caller then falls back to a suggested one. */
export const loadSampleAgentModelName = async (agentConfigPath: string): Promise<string | null> => {
  const text = await fetchSampleText(agentConfigPath);
  let config: Record<string, unknown> | undefined;
  try {
    config = YAML.parse(text) as Record<string, unknown> | undefined;
  } catch {
    return null;
  }

  const natLlm = asObject(asObject(config?.llms)?.['llm']);
  if (natLlm) return bareModelName(natLlm['model_name']);

  const fabricDefault = asObject(asObject(config?.models)?.['default']);
  if (fabricDefault) return bareModelName(fabricDefault['model']);

  return null;
};
