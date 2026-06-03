// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getAssistantPartsFromClaudeEvent,
  getAssistantTextFromClaudeEvent,
  parseJsonObject,
  parseSseChunk,
} from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import { websiteLogger } from '@studio/util/logger';

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

  it('extracts assistant reasoning, text, and tool-call parts from Claude Code events', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
          { type: 'thinking', thinking: 'checking the repo\nthen reading the route' },
          { type: 'text', text: 'I can check that.' },
          { type: 'tool_use', id: 'toolu_1', name: 'Bash', input: { command: 'pwd' } },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([
      { type: 'reasoning', text: 'checking the repo\nthen reading the route' },
      { type: 'text', text: 'I can check that.' },
      {
        type: 'tool-call',
        toolCallId: 'toolu_1',
        toolName: 'Bash',
        args: { command: 'pwd' },
        argsText: '{"command":"pwd"}',
      },
    ]);
    expect(getAssistantTextFromClaudeEvent(event)).toBe(
      'checking the repo\nthen reading the routeI can check that.'
    );
  });

  it('returns undefined and logs when JSON parsing fails', () => {
    const loggerSpy = vi.spyOn(websiteLogger, 'error').mockImplementation(() => undefined);

    expect(parseJsonObject('{')).toBeUndefined();
    expect(loggerSpy).toHaveBeenCalledWith(
      expect.stringContaining('Failed to parse Claude Code stream JSON')
    );

    loggerSpy.mockRestore();
  });
});
