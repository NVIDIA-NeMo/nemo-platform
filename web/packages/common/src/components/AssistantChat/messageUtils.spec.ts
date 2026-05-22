// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import { getOpenAIMessages } from '@nemo/common/src/components/AssistantChat/messageUtils';

const createMessage = (role: ThreadMessageLike['role'], text: string): ThreadMessageLike => ({
  id: `${role}-${text}`,
  role,
  content: [{ type: 'text', text }],
});

describe('getOpenAIMessages', () => {
  it('filters empty content for all OpenAI message roles', () => {
    const messages = [
      createMessage('system', ''),
      createMessage('user', ''),
      createMessage('assistant', ''),
      createMessage('user', 'Hello'),
    ];

    expect(getOpenAIMessages(messages)).toEqual([{ role: 'user', content: 'Hello' }]);
  });

  it('replaces existing system messages when a system prompt is provided', () => {
    const messages = [
      createMessage('system', 'Original system prompt'),
      createMessage('user', 'Hello'),
    ];

    expect(getOpenAIMessages(messages, 'Replacement system prompt')).toEqual([
      { role: 'system', content: 'Replacement system prompt' },
      { role: 'user', content: 'Hello' },
    ]);
  });

  it('splits assistant tool-call parts into assistant + tool messages', () => {
    const messages: ThreadMessageLike[] = [
      createMessage('user', 'render a chart'),
      {
        id: 'assistant-1',
        role: 'assistant',
        content: [
          { type: 'text', text: 'Rendering now.' },
          {
            type: 'tool-call',
            toolCallId: 'call_abc',
            toolName: 'example_tool',
            argsText: '{"html":"<p>hi</p>"}',
            result: { rendered: true },
          },
        ],
      },
    ];

    expect(getOpenAIMessages(messages)).toEqual([
      { role: 'user', content: 'render a chart' },
      {
        role: 'assistant',
        content: 'Rendering now.',
        tool_calls: [
          {
            id: 'call_abc',
            type: 'function',
            function: { name: 'example_tool', arguments: '{"html":"<p>hi</p>"}' },
          },
        ],
      },
      {
        role: 'tool',
        tool_call_id: 'call_abc',
        content: '{"rendered":true}',
      },
    ]);
  });

  it('emits assistant tool_calls without a tool message until a result is attached', () => {
    const messages: ThreadMessageLike[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: [
          {
            type: 'tool-call',
            toolCallId: 'call_pending',
            toolName: 'web_search',
            argsText: '{"query":"weather"}',
          },
        ],
      },
    ];

    const result = getOpenAIMessages(messages);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      role: 'assistant',
      content: null,
      tool_calls: [
        {
          id: 'call_pending',
          type: 'function',
          function: { name: 'web_search', arguments: '{"query":"weather"}' },
        },
      ],
    });
  });
});
