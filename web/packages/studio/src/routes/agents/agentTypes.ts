// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';

export const NAT_WORKFLOW_CONFIG_FORMAT = 'nat-workflow-v1';
export const EXTERNAL_ENDPOINT_CONFIG_FORMAT = 'external-endpoint-v1';
export const EXTERNAL_ENDPOINT_PROTOCOL = 'nat-http-v1';

export const isExternalEndpointAgent = (agent: Pick<Agent, 'config_format'>): boolean =>
  agent.config_format === EXTERNAL_ENDPOINT_CONFIG_FORMAT;

export const getExternalEndpoint = (
  agent: Pick<Agent, 'config' | 'config_format'>
): string | null => {
  if (!isExternalEndpointAgent(agent)) return null;
  const endpoint = agent.config?.['endpoint_url'];
  return typeof endpoint === 'string' && endpoint.length > 0 ? endpoint : null;
};

export const getAgentEvaluationTarget = (
  agent: Pick<Agent, 'name' | 'config' | 'config_format'>
): string | null => getExternalEndpoint(agent) ?? agent.name ?? null;
