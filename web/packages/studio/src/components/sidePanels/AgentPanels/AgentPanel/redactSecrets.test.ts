// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { redactSecrets } from '@studio/components/sidePanels/AgentPanels/AgentPanel/redactSecrets';

describe('redactSecrets', () => {
  it('masks credential-like keys anywhere in the tree', () => {
    expect(
      redactSecrets({
        llms: { llm: { _type: 'openai', model_name: 'gpt-4o', api_key: 'sk-secret' } },
        auth: { token: 'abc', bearer_secret: 'xyz' },
        password: 'hunter2',
      })
    ).toEqual({
      llms: { llm: { _type: 'openai', model_name: 'gpt-4o', api_key: '***' } },
      auth: { token: '***', bearer_secret: '***' },
      password: '***',
    });
  });

  it('leaves non-secret values and structure intact', () => {
    const input = { workflow: { _type: 'react_agent', tool_names: ['a', 'b'] } };
    expect(redactSecrets(input)).toEqual(input);
  });

  it('handles arrays and primitives', () => {
    expect(redactSecrets([{ api_key: 'k' }, 'plain'])).toEqual([{ api_key: '***' }, 'plain']);
    expect(redactSecrets(undefined)).toBeUndefined();
  });
});
