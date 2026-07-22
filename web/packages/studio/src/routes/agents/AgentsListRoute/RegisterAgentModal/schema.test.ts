// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  REGISTRATION_TYPE_EXTERNAL,
  REGISTRATION_TYPE_NAT,
  registerAgentSchema,
  workflowConfigFromForm,
} from '@studio/routes/agents/AgentsListRoute/RegisterAgentModal/schema';

describe('registerAgentSchema', () => {
  it('accepts and parses a NAT workflow YAML object', () => {
    const source = `
llms:
  llm:
    _type: openai
    model_name: nvidia-nemotron
workflow:
  _type: react_agent
  llm_name: llm
`;

    expect(
      registerAgentSchema.safeParse({
        registrationType: REGISTRATION_TYPE_NAT,
        name: 'support-agent',
        description: '',
        workflowConfig: source,
        endpointUrl: '',
      }).success
    ).toBe(true);
    expect(workflowConfigFromForm(source)).toMatchObject({
      llms: { llm: { model_name: 'nvidia-nemotron' } },
      workflow: { _type: 'react_agent' },
    });
  });

  it('rejects invalid YAML and non-object documents', () => {
    expect(
      registerAgentSchema.safeParse({
        registrationType: REGISTRATION_TYPE_NAT,
        name: 'support-agent',
        description: '',
        workflowConfig: '[',
        endpointUrl: '',
      }).success
    ).toBe(false);
    expect(
      registerAgentSchema.safeParse({
        registrationType: REGISTRATION_TYPE_NAT,
        name: 'support-agent',
        description: '',
        workflowConfig: '- one\n- two',
        endpointUrl: '',
      }).success
    ).toBe(false);
  });

  it('accepts HTTP endpoints and rejects unsupported URL schemes', () => {
    expect(
      registerAgentSchema.safeParse({
        registrationType: REGISTRATION_TYPE_EXTERNAL,
        name: 'remote-agent',
        description: '',
        workflowConfig: '',
        endpointUrl: 'https://agents.example.com/v1',
      }).success
    ).toBe(true);
    expect(
      registerAgentSchema.safeParse({
        registrationType: REGISTRATION_TYPE_EXTERNAL,
        name: 'remote-agent',
        description: '',
        workflowConfig: '',
        endpointUrl: 'file:///tmp/agent',
      }).success
    ).toBe(false);
  });
});
