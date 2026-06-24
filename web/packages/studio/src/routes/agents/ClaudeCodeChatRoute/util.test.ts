// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME } from '@studio/routes/agents/ClaudeCodeChatRoute/jobProgressConsts';
import {
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
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
      chat_artifacts: { selections: [], files: [], links: [], jobs: [], tools: [] },
      items: [
        { kind: 'user', text: 'check the repo' },
        {
          kind: 'assistant',
          parts: [
            { type: 'text', text: 'I found the route.' },
            { type: 'tool_use', name: 'AskUserQuestion', input: { question: 'Continue?' } },
            { type: 'tool_use', name: 'Bash', input: { command: 'pwd' } },
            { type: 'tool_use', name: 'Grep', input: { pattern: 'TODO' } },
            { type: 'tool_use', name: 'Read', input: { file_path: 'README.md' } },
            { type: 'text', text: 'I updated the route.\n\nTests passed.' },
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
            { type: 'text', text: 'I found another route.' },
            { type: 'tool_use', name: 'AskUserQuestion', input: { question: 'Continue?' } },
            { type: 'tool_use', name: 'Bash', input: { command: 'pwd' } },
            { type: 'tool_use', name: 'Grep', input: { pattern: 'TODO' } },
            { type: 'tool_use', name: 'Read', input: { file_path: 'package.json' } },
          ],
        },
      ],
    };

    const messages = getClaudeCodeHistoryMessages(history);

    expect(messages).toHaveLength(4);
    expect(messages[0]).toEqual({
      id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-0',
      role: 'user',
      content: [{ type: 'text', text: 'check the repo' }],
    });
    expect(messages[1]).toMatchObject({
      id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-1',
      role: 'assistant',
      content: [
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
          args: {
            text: 'I found the route.',
          },
        },
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { args: { question: 'Continue?' }, toolName: 'AskUserQuestion' },
              { args: { command: 'pwd' }, toolName: 'Bash' },
              { args: { pattern: 'TODO' }, toolName: 'Grep' },
              { args: { file_path: 'README.md' }, toolName: 'Read' },
            ],
          },
        },
        { type: 'text', text: 'I updated the route.\n\nTests passed.' },
      ],
      status: { type: 'complete', reason: 'stop' },
    });
    expect(messages[2]).toMatchObject({
      id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-2',
      role: 'assistant',
      content: [
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { args: { status: 'done' }, toolName: 'TaskUpdate' },
              { args: { pattern: 'TODO' }, toolName: 'Grep' },
              { args: { question: 'Continue?' }, toolName: 'AskUserQuestion' },
              { args: { query: 'TODO' }, toolName: 'FindFiles' },
              { args: { task: 'check' }, toolName: 'TaskCreate' },
              { args: { query: 'read' }, toolName: 'ToolSearch' },
            ],
          },
        },
      ],
      status: { type: 'complete', reason: 'stop' },
    });
    expect(messages[3]).toMatchObject({
      id: '2dc6e5a6-acd7-43bf-b128-c9fd5cf6eb9a-3',
      role: 'assistant',
      content: [
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
          args: {
            text: 'I found another route.',
          },
        },
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { args: { question: 'Continue?' }, toolName: 'AskUserQuestion' },
              { args: { command: 'pwd' }, toolName: 'Bash' },
              { args: { pattern: 'TODO' }, toolName: 'Grep' },
              { args: { file_path: 'package.json' }, toolName: 'Read' },
            ],
          },
        },
      ],
      status: { type: 'complete', reason: 'stop' },
    });
  });

  it('combines consecutive tool-only assistant transcript items', () => {
    const history: ClaudeCodeSessionHistory = {
      session_id: 'session-1',
      chat_artifacts: { selections: [], files: [], links: [], jobs: [], tools: [] },
      items: [
        { kind: 'user', text: 'map the repo' },
        {
          kind: 'assistant',
          parts: [{ type: 'tool_use', name: 'Bash', input: { description: 'list files' } }],
        },
        {
          kind: 'assistant',
          parts: [{ type: 'tool_use', name: 'Glob', input: { pattern: '*' } }],
        },
        {
          kind: 'assistant',
          parts: [{ type: 'text', text: 'Glob hit node_modules.' }],
        },
        {
          kind: 'assistant',
          parts: [{ type: 'tool_use', name: 'Glob', input: { pattern: 'packages/*' } }],
        },
        {
          kind: 'assistant',
          parts: [{ type: 'tool_use', name: 'Glob', input: { pattern: 'services/*' } }],
        },
      ],
    };

    const messages = getClaudeCodeHistoryMessages(history);

    expect(messages).toHaveLength(4);
    expect(messages[1]).toMatchObject({
      role: 'assistant',
      content: [
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { args: { description: 'list files' }, toolName: 'Bash' },
              { args: { pattern: '*' }, toolName: 'Glob' },
            ],
          },
        },
      ],
    });
    expect(messages[2]).toMatchObject({
      role: 'assistant',
      content: [{ type: 'text', text: 'Glob hit node_modules.' }],
    });
    expect(messages[3]).toMatchObject({
      role: 'assistant',
      content: [
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { args: { pattern: 'packages/*' }, toolName: 'Glob' },
              { args: { pattern: 'services/*' }, toolName: 'Glob' },
            ],
          },
        },
      ],
    });
  });

  it('keeps stored job progress tool calls visible in history', () => {
    const history: ClaudeCodeSessionHistory = {
      session_id: 'session-1',
      chat_artifacts: { selections: [], files: [], links: [], jobs: [], tools: [] },
      items: [
        { kind: 'user', text: 'evaluate my agent' },
        {
          kind: 'assistant',
          parts: [
            { type: 'tool_use', name: 'Bash', input: { command: 'pwd' } },
            {
              type: 'tool_use',
              id: ' toolu_job ',
              name: CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
              input: { job_name: 'studio-job-1' },
            },
            { type: 'tool_use', name: 'Read', input: { file_path: 'README.md' } },
          ],
        },
      ],
    };

    const messages = getClaudeCodeHistoryMessages(history);

    expect(messages[1]).toMatchObject({
      role: 'assistant',
      content: [
        { type: 'tool-call', toolName: 'Bash' },
        {
          type: 'tool-call',
          toolCallId: 'toolu_job',
          toolName: CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
          args: { job_name: 'studio-job-1' },
        },
        { type: 'tool-call', toolName: 'Read' },
      ],
    });
  });
});
