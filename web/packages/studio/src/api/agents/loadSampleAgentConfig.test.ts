// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { loadSampleAgentConfig } from '@studio/api/agents/loadSampleAgentConfig';

const AGENT_YAML = `functions:
  email_phishing_analyzer:
    _type: email_phishing_analyzer
    llm: llm
llms:
  llm:
    _type: openai
    model_name: \${NEMO_DEFAULT_MODEL}
    temperature: 0.0
workflow:
  _type: react_agent
  tool_names: [email_phishing_analyzer]
`;

const mockFetchText = (body: string, ok = true) =>
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok,
    statusText: ok ? 'OK' : 'Not Found',
    text: () => Promise.resolve(body),
  } as Response);

describe('loadSampleAgentConfig', () => {
  afterEach(() => vi.restoreAllMocks());

  it('parses the YAML and injects the selected model, preserving the rest', async () => {
    mockFetchText(AGENT_YAML);
    const config = (await loadSampleAgentConfig('sample-agents/x/agent.yml', 'my-model')) as {
      functions: Record<string, { _type: string }>;
      llms: { llm: { model_name: string; _type: string } };
      workflow: { _type: string };
    };
    expect(config.llms.llm.model_name).toBe('my-model');
    expect(config.llms.llm._type).toBe('openai');
    expect(config.functions.email_phishing_analyzer._type).toBe('email_phishing_analyzer');
    expect(config.workflow._type).toBe('react_agent');
  });

  it('throws when the config is missing llms.llm', async () => {
    mockFetchText('workflow:\n  _type: react_agent\n');
    await expect(loadSampleAgentConfig('sample-agents/x/agent.yml', 'm')).rejects.toThrow(
      /missing llms\.llm/
    );
  });

  it('throws when llms.llm is not an object', async () => {
    // A non-object llm (here a string) would otherwise crash the model_name
    // assignment with a TypeError instead of the clean guard error.
    mockFetchText('llms:\n  llm: some-string\n');
    await expect(loadSampleAgentConfig('sample-agents/x/agent.yml', 'm')).rejects.toThrow(
      /missing llms\.llm/
    );
  });

  it('throws when the fetch fails', async () => {
    mockFetchText('', false);
    await expect(loadSampleAgentConfig('sample-agents/x/agent.yml', 'm')).rejects.toThrow(
      /Failed to fetch/
    );
  });
});
