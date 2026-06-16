// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';

import { getOpenAIMessages } from './messageUtils';

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
});
