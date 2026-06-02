// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getAssistantTextFromClaudeEvent,
  parseSseChunk,
} from '@studio/routes/agents/ClaudeCodeChatRoute/stream';

describe('Claude Code stream utilities', () => {
  it('parses SSE events and preserves incomplete trailing data', () => {
    const parsed = parseSseChunk(
      [
        'data: {"type":"assistant"}',
        '',
        'event: custom_event',
        'data: {"request_id":"req-1"}',
        '',
        'event: don',
      ].join('\n')
    );

    expect(parsed.events).toEqual([
      { event: undefined, data: '{"type":"assistant"}' },
      { event: 'custom_event', data: '{"request_id":"req-1"}' },
    ]);
    expect(parsed.rest).toBe('event: don');
  });

  it('extracts assistant text and tool summaries from Claude Code events', () => {
    expect(
      getAssistantTextFromClaudeEvent({
        type: 'assistant',
        message: {
          content: [
            { type: 'text', text: 'I can check that.' },
            { type: 'tool_use', name: 'Bash' },
          ],
        },
      })
    ).toBe('I can check that.\n\nUsing Bash...');
  });
});
