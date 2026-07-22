// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getAgentEvaluationTarget,
  getExternalEndpoint,
  isExternalEndpointAgent,
} from '@studio/routes/agents/agentTypes';

describe('agentTypes', () => {
  it('resolves registered external agents to their endpoint for evaluation', () => {
    const agent = {
      name: 'remote-agent',
      config_format: 'external-endpoint-v1',
      config: { endpoint_url: 'https://agents.example.com/v1', protocol: 'nat-http-v1' },
    };

    expect(isExternalEndpointAgent(agent)).toBe(true);
    expect(getExternalEndpoint(agent)).toBe('https://agents.example.com/v1');
    expect(getAgentEvaluationTarget(agent)).toBe('https://agents.example.com/v1');
  });

  it('keeps managed agents addressed by name', () => {
    expect(
      getAgentEvaluationTarget({
        name: 'managed-agent',
        config_format: 'nat-workflow-v1',
        config: { workflow: { _type: 'react_agent' } },
      })
    ).toBe('managed-agent');
  });
});
