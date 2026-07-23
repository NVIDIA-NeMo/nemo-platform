// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { humanizeKey } from '@studio/routes/agents/AgentDetailRoute/configFormat';
import { ConfigValue } from '@studio/routes/agents/AgentDetailRoute/ConfigValue';
import { render, screen } from '@studio/tests/util/render';

describe('humanizeKey', () => {
  it.each([
    ['_type', 'Type'],
    ['model_name', 'Model Name'],
    ['llm_name', 'LLM Name'],
    ['base_url', 'Base URL'],
    ['parseAgentResponseMaxRetries', 'Parse Agent Response Max Retries'],
  ])('humanizes %s -> %s', (input, expected) => {
    expect(humanizeKey(input)).toBe(expected);
  });
});

describe('ConfigValue', () => {
  it('renders a scalar as a single row', () => {
    render(<ConfigValue label="verbose" value={false} />);
    expect(screen.getByText('Verbose')).toBeInTheDocument();
    expect(screen.getByText('false')).toBeInTheDocument();
  });

  it('joins a scalar array', () => {
    render(<ConfigValue label="tool_names" value={['wiki', 'clock']} />);
    expect(screen.getByText('Tool Names')).toBeInTheDocument();
    expect(screen.getByText('wiki, clock')).toBeInTheDocument();
  });

  it('masks sensitive keys', () => {
    render(<ConfigValue label="api_key" value="super-secret" />);
    expect(screen.queryByText('super-secret')).not.toBeInTheDocument();
    expect(screen.getByText('••••••••')).toBeInTheDocument();
  });

  it.each(['max_tokens', 'maxTokens'])('does not mask token-count key %s', (label) => {
    render(<ConfigValue label={label} value={4096} />);
    expect(screen.getByText('4096')).toBeInTheDocument();
    expect(screen.queryByText('••••••••')).not.toBeInTheDocument();
  });

  it('recurses into nested objects', () => {
    render(<ConfigValue label="llm" value={{ _type: 'openai', temperature: 0 }} />);
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('openai')).toBeInTheDocument();
    expect(screen.getByText('Temperature')).toBeInTheDocument();
  });
});
