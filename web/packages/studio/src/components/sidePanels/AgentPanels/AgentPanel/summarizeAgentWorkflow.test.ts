// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { summarizeAgentWorkflow } from '@studio/components/sidePanels/AgentPanels/AgentPanel/summarizeAgentWorkflow';

describe('summarizeAgentWorkflow', () => {
  it('returns empty summary for undefined config', () => {
    expect(summarizeAgentWorkflow(undefined)).toEqual({
      workflowType: undefined,
      llmName: undefined,
      models: [],
      tools: [],
    });
  });

  it('extracts workflow type, model, and flags wired tools', () => {
    const config: AgentConfig = {
      functions: {
        calculator: { _type: 'calculator' },
        current_datetime: { _type: 'current_datetime' },
        unused: { _type: 'internet_search' },
      },
      llms: { llm: { _type: 'openai', model_name: 'gpt-4o' } },
      workflow: {
        _type: 'react_agent',
        llm_name: 'llm',
        tool_names: ['calculator', 'current_datetime'],
      },
    };
    expect(summarizeAgentWorkflow(config)).toEqual({
      workflowType: 'react_agent',
      llmName: 'llm',
      models: ['gpt-4o'],
      tools: [
        { name: 'calculator', type: 'calculator', wired: true },
        { name: 'current_datetime', type: 'current_datetime', wired: true },
        { name: 'unused', type: 'internet_search', wired: false },
      ],
    });
  });

  it('dedupes repeated model names across llms', () => {
    const config: AgentConfig = {
      llms: {
        a: { _type: 'openai', model_name: 'gpt-4o' },
        b: { _type: 'openai', model_name: 'gpt-4o' },
      },
      workflow: { _type: 'react_agent' },
    };
    expect(summarizeAgentWorkflow(config).models).toEqual(['gpt-4o']);
  });
});
