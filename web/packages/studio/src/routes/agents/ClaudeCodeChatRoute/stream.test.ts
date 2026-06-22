// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME } from '@studio/routes/agents/ClaudeCodeChatRoute/jobProgressConsts';
import {
  getAssistantPartsFromClaudeEvent,
  getAssistantTextFromClaudeEvent,
  parseJsonObject,
  parseSseChunk,
} from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import { CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME } from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import { logger } from '@studio/util/logger';

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

  it('extracts assistant text and tool-call parts from Claude Code events', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
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
      { type: 'text', text: 'I can check that.' },
      {
        type: 'tool-call',
        toolCallId: 'claude-code-subtle-tools-toolu_question-toolu_2',
        toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
        args: {
          actions: [
            {
              args: { question: 'Continue?' },
              toolCallId: 'toolu_question',
              toolName: 'AskUserQuestion',
            },
            { args: { status: 'done' }, toolCallId: 'toolu_hidden', toolName: 'TaskUpdate' },
            { args: { command: 'pwd' }, toolCallId: 'toolu_1', toolName: 'Bash' },
            { args: { pattern: 'TODO' }, toolCallId: 'toolu_grep', toolName: 'Grep' },
            { args: { file_path: 'README.md' }, toolCallId: 'toolu_2', toolName: 'Read' },
          ],
        },
        argsText:
          '{"actions":[{"args":{"question":"Continue?"},"toolCallId":"toolu_question","toolName":"AskUserQuestion"},{"args":{"status":"done"},"toolCallId":"toolu_hidden","toolName":"TaskUpdate"},{"args":{"command":"pwd"},"toolCallId":"toolu_1","toolName":"Bash"},{"args":{"pattern":"TODO"},"toolCallId":"toolu_grep","toolName":"Grep"},{"args":{"file_path":"README.md"},"toolCallId":"toolu_2","toolName":"Read"}]}',
      },
    ]);
    expect(getAssistantTextFromClaudeEvent(event)).toBe('I can check that.');
  });

  it('preserves subtle Claude Code tool calls from streamed parts', () => {
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

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([
      {
        type: 'tool-call',
        toolCallId: 'claude-code-subtle-tools-toolu_1-toolu_4',
        toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
        args: {
          actions: [
            { args: { command: 'pwd' }, toolCallId: 'toolu_1', toolName: 'Bash' },
            { args: { status: 'done' }, toolCallId: 'toolu_2', toolName: 'TaskUpdate' },
            { args: { pattern: 'TODO' }, toolCallId: 'toolu_3', toolName: 'Grep' },
            { args: { query: 'TODO' }, toolCallId: 'toolu_find', toolName: 'FindFiles' },
            { args: { task: 'check' }, toolCallId: 'toolu_task', toolName: 'TaskCreate' },
            { args: { query: 'read' }, toolCallId: 'toolu_search', toolName: 'ToolSearch' },
            { args: { question: 'Continue?' }, toolCallId: 'toolu_4', toolName: 'AskUserQuestion' },
          ],
        },
        argsText:
          '{"actions":[{"args":{"command":"pwd"},"toolCallId":"toolu_1","toolName":"Bash"},{"args":{"status":"done"},"toolCallId":"toolu_2","toolName":"TaskUpdate"},{"args":{"pattern":"TODO"},"toolCallId":"toolu_3","toolName":"Grep"},{"args":{"query":"TODO"},"toolCallId":"toolu_find","toolName":"FindFiles"},{"args":{"task":"check"},"toolCallId":"toolu_task","toolName":"TaskCreate"},{"args":{"query":"read"},"toolCallId":"toolu_search","toolName":"ToolSearch"},{"args":{"question":"Continue?"},"toolCallId":"toolu_4","toolName":"AskUserQuestion"}]}',
      },
    ]);
  });

  it('groups unknown non-file-change tool calls with other subtle streamed parts', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
          {
            type: 'tool_use',
            id: 'toolu_inspect',
            name: 'InspectWorkspace',
            input: { query: 'symbols' },
          },
          { type: 'tool_use', id: 'toolu_read', name: 'Read', input: { file_path: 'README.md' } },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
        args: {
          actions: [
            {
              args: { query: 'symbols' },
              toolCallId: 'toolu_inspect',
              toolName: 'InspectWorkspace',
            },
            { args: { file_path: 'README.md' }, toolCallId: 'toolu_read', toolName: 'Read' },
          ],
        },
      },
    ]);
  });

  it('keeps the job progress card out of subtle streamed tool groups', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
          { type: 'tool_use', id: 'toolu_bash', name: 'Bash', input: { command: 'pwd' } },
          {
            type: 'tool_use',
            id: 'toolu_job',
            name: CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
            input: { job_name: 'studio-job-1' },
          },
          { type: 'tool_use', id: 'toolu_read', name: 'Read', input: { file_path: 'README.md' } },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toEqual([
      {
        type: 'tool-call',
        toolCallId: 'toolu_bash',
        toolName: 'Bash',
        args: { command: 'pwd' },
        argsText: '{"command":"pwd"}',
      },
      {
        type: 'tool-call',
        toolCallId: 'toolu_job',
        toolName: CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
        args: { job_name: 'studio-job-1' },
        argsText: '{"job_name":"studio-job-1"}',
      },
      {
        type: 'tool-call',
        toolCallId: 'toolu_read',
        toolName: 'Read',
        args: { file_path: 'README.md' },
        argsText: '{"file_path":"README.md"}',
      },
    ]);
  });

  it('combines subtle streamed tool calls across whitespace-only text parts', () => {
    const event = {
      type: 'assistant',
      message: {
        content: [
          { type: 'tool_use', id: 'toolu_bash', name: 'Bash', input: { command: 'pwd' } },
          { type: 'text', text: '\n\n' },
          { type: 'tool_use', id: 'toolu_glob', name: 'Glob', input: { pattern: '*' } },
        ],
      },
    };

    expect(getAssistantPartsFromClaudeEvent(event)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
        args: {
          actions: [
            { args: { command: 'pwd' }, toolCallId: 'toolu_bash', toolName: 'Bash' },
            { args: { pattern: '*' }, toolCallId: 'toolu_glob', toolName: 'Glob' },
          ],
        },
      },
    ]);
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
    const loggerSpy = vi.spyOn(logger, 'error').mockImplementation(() => undefined);

    expect(parseJsonObject('{')).toBeUndefined();
    expect(loggerSpy).toHaveBeenCalledWith(
      expect.stringContaining('Failed to parse Claude Code stream JSON'),
      expect.any(Error)
    );

    loggerSpy.mockRestore();
  });
});
