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
          {
            type: 'tool_use',
            id: 'toolu_question',
            name: 'AskUserQuestion',
            input: { question: 'Continue?' },
          },
          { type: 'tool_use', id: 'toolu_hidden', name: 'TaskUpdate', input: { status: 'done' } },
          { type: 'tool_use', id: 'toolu_1', name: 'Bash', input: { command: 'pwd' } },
          { type: 'tool_use', id: 'toolu_grep', name: 'Grep', input: { pattern: 'TODO' } },
          { type: 'tool_use', id: 'toolu_2', name: 'Read', input: { file_path: 'README.md' } },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([
      { type: 'reasoning', text: 'checking the repo\nthen reading the route' },
      { type: 'text', text: 'I can check that.' },
      {
        type: 'tool-call',
        toolCallId: 'toolu_2',
        toolName: 'Read',
        args: { file_path: 'README.md' },
        argsText: '{"file_path":"README.md"}',
      },
    ]);
    expect(getAssistantTextFromClaudeEvent(event)).toBe(
      'checking the repo\nthen reading the routeI can check that.'
    );
  });

  it('omits hidden Claude Code tool calls from streamed parts', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
          { type: 'tool_use', id: 'toolu_1', name: 'Bash', input: { command: 'pwd' } },
          { type: 'tool_use', id: 'toolu_2', name: 'TaskUpdate', input: { status: 'done' } },
          { type: 'tool_use', id: 'toolu_3', name: 'Grep', input: { pattern: 'TODO' } },
          { type: 'tool_use', id: 'toolu_find', name: 'FindFiles', input: { query: 'TODO' } },
          { type: 'tool_use', id: 'toolu_task', name: 'TaskCreate', input: { task: 'check' } },
          { type: 'tool_use', id: 'toolu_search', name: 'ToolSearch', input: { query: 'read' } },
          {
            type: 'tool_use',
            id: 'toolu_4',
            name: 'AskUserQuestion',
            input: { question: 'Continue?' },
          },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([]);
  });

  it('scopes fallback streamed tool-call ids to the Claude message id', () => {
    const event = {
      type: 'assistant',
      message: {
        id: 'msg_123',
        content: [{ type: 'tool_use', name: 'Read', input: { file_path: 'README.md' } }],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([
      {
        type: 'tool-call',
        toolCallId: 'claude-code-tool-msg_123-Read-0',
        toolName: 'Read',
        args: { file_path: 'README.md' },
        argsText: '{"file_path":"README.md"}',
      },
    ]);
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
