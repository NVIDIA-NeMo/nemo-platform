// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodeSessionHistory } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import {
  getClaudeCodeChatRouteForSession,
  getClaudeCodeHistoryMessages,
  getSelectedClaudeCodeSessionId,
} from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';

describe('Claude Code utilities', () => {
  it('builds and reads selected session URLs', () => {
    const workspace = 'default';
    const sessionId = '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a';

    expect(getClaudeCodeChatRouteForSession(workspace, sessionId)).toBe(
      `${getClaudeCodeChatRoute(workspace)}?session=${sessionId}`
    );
    expect(getSelectedClaudeCodeSessionId(`?session=${sessionId}`)).toBe(sessionId);
    expect(getSelectedClaudeCodeSessionId('?session=')).toBeUndefined();
  });

  it('converts stored transcript items to assistant-ui messages', () => {
    const history: ClaudeCodeSessionHistory = {
      session_id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a',
      items: [
        { kind: 'user', text: 'check the repo' },
        {
          kind: 'assistant',
          parts: [
            { type: 'thinking', thinking: 'checking' },
            { type: 'text', text: 'I found the route.' },
            { type: 'tool_use', name: 'AskUserQuestion', input: { question: 'Continue?' } },
            { type: 'tool_use', name: 'Bash', input: { command: 'pwd' } },
            { type: 'tool_use', name: 'Grep', input: { pattern: 'TODO' } },
            { type: 'tool_use', name: 'Read', input: { file_path: 'README.md' } },
          ],
        },
        {
          kind: 'assistant',
          parts: [
            { type: 'tool_use', name: 'TaskUpdate', input: { status: 'done' } },
            { type: 'tool_use', name: 'Grep', input: { pattern: 'TODO' } },
            { type: 'tool_use', name: 'AskUserQuestion', input: { question: 'Continue?' } },
            { type: 'tool_use', name: 'FindFiles', input: { query: 'TODO' } },
            { type: 'tool_use', name: 'TaskCreate', input: { task: 'check' } },
            { type: 'tool_use', name: 'ToolSearch', input: { query: 'read' } },
          ],
        },
        {
          kind: 'assistant',
          parts: [
            { type: 'thinking', thinking: 'checking again' },
            { type: 'text', text: 'I found another route.' },
            { type: 'tool_use', name: 'AskUserQuestion', input: { question: 'Continue?' } },
            { type: 'tool_use', name: 'Bash', input: { command: 'pwd' } },
            { type: 'tool_use', name: 'Grep', input: { pattern: 'TODO' } },
            { type: 'tool_use', name: 'Read', input: { file_path: 'package.json' } },
          ],
        },
      ],
    };

    expect(getClaudeCodeHistoryMessages(history)).toEqual([
      {
        id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-0',
        role: 'user',
        content: [{ type: 'text', text: 'check the repo' }],
      },
      {
        id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-1',
        role: 'assistant',
        content: [
          { type: 'reasoning', text: 'checking' },
          { type: 'text', text: 'I found the route.' },
          {
            type: 'tool-call',
            toolCallId:
              'claude-history-tool-2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-1-Read-5',
            toolName: 'Read',
            args: { file_path: 'README.md' },
            argsText: '{"file_path":"README.md"}',
          },
        ],
        status: { type: 'complete', reason: 'stop' },
      },
      {
        id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-3',
        role: 'assistant',
        content: [
          { type: 'reasoning', text: 'checking again' },
          { type: 'text', text: 'I found another route.' },
          {
            type: 'tool-call',
            toolCallId:
              'claude-history-tool-2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-3-Read-5',
            toolName: 'Read',
            args: { file_path: 'package.json' },
            argsText: '{"file_path":"package.json"}',
          },
        ],
        status: { type: 'complete', reason: 'stop' },
      },
    ]);
  });
});
