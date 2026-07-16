// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parseAgentConfig } from '@studio/api/agents/parseAgentConfig';

describe('parseAgentConfig', () => {
  it('parses a NAT workflow YAML into a config dict', () => {
    const config = parseAgentConfig(`
llms:
  llm:
    _type: openai
    model_name: gpt-4o
workflow:
  _type: react_agent
  llm_name: llm
`);
    expect(config).toMatchObject({
      workflow: { _type: 'react_agent', llm_name: 'llm' },
      llms: { llm: { model_name: 'gpt-4o' } },
    });
  });

  it('accepts JSON input (YAML is a JSON superset)', () => {
    expect(parseAgentConfig('{"workflow": {"_type": "react_agent"}}')).toEqual({
      workflow: { _type: 'react_agent' },
    });
  });

  it('rejects empty input', () => {
    expect(() => parseAgentConfig('   ')).toThrow(/paste your nat workflow config/i);
  });

  it('rejects invalid YAML', () => {
    expect(() => parseAgentConfig('foo: [1, 2')).toThrow(/not valid yaml/i);
  });

  it('rejects a scalar', () => {
    expect(() => parseAgentConfig('just a string')).toThrow(/must be a yaml mapping/i);
  });

  it('rejects a config with no workflow section', () => {
    expect(() => parseAgentConfig('llms:\n  llm:\n    _type: openai')).toThrow(
      /missing.*workflow/i
    );
  });
});
