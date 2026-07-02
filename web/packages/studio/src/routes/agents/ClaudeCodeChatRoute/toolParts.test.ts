// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart } from '@assistant-ui/react';
import {
  CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
  getClaudeCodeCompletedMessageParts,
  STUDIO_MESSAGE_SUMMARY_END,
  STUDIO_MESSAGE_SUMMARY_START,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';

describe('Claude Code tool parts', () => {
  it('collapses details before a Studio summary block and shows only the summary text', () => {
    const bashPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_bash',
      toolName: 'Bash',
      args: { command: 'pwd' },
      argsText: '{"command":"pwd"}',
    };
    const parts: readonly ThreadAssistantMessagePart[] = [
      { type: 'text', text: 'I inspected the repo first.' },
      bashPart,
      {
        type: 'text',
        text: [
          'I found the prompt builder and updated it.',
          '',
          STUDIO_MESSAGE_SUMMARY_START,
          'worked_for: unknown',
          'summary: Updated Studio so completed coding-agent messages collapse to a short summary.',
          'details_label: worked for unknown',
          STUDIO_MESSAGE_SUMMARY_END,
        ].join('\n'),
      },
    ];

    const completedParts = getClaudeCodeCompletedMessageParts(parts, { elapsedMs: 123_000 });

    expect(completedParts).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
        args: {
          label: 'worked for 2m 3s',
          parts: [
            { type: 'text', text: 'I inspected the repo first.' },
            { type: 'tool-call', toolName: 'Bash', args: { command: 'pwd' } },
            { type: 'text', text: 'I found the prompt builder and updated it.' },
          ],
        },
      },
      {
        type: 'text',
        text: 'Updated Studio so completed coding-agent messages collapse to a short summary.',
      },
    ]);
  });

  it('removes the Studio summary markers when there are no details to collapse', () => {
    const parts: readonly ThreadAssistantMessagePart[] = [
      {
        type: 'text',
        text: [
          STUDIO_MESSAGE_SUMMARY_START,
          'worked_for: 4s',
          'summary: Ready for the next step.',
          'details_label: worked for 4s',
          STUDIO_MESSAGE_SUMMARY_END,
        ].join('\n'),
      },
    ];

    expect(getClaudeCodeCompletedMessageParts(parts)).toEqual([
      { type: 'text', text: 'Ready for the next step.' },
    ]);
  });

  it('uses a neutral details label when the work time is unknown', () => {
    const parts: readonly ThreadAssistantMessagePart[] = [
      { type: 'text', text: 'Detailed work that should be collapsed.' },
      {
        type: 'text',
        text: [
          STUDIO_MESSAGE_SUMMARY_START,
          'worked_for: unknown',
          'summary: Ready for the next step.',
          'details_label: worked for unknown',
          STUDIO_MESSAGE_SUMMARY_END,
        ].join('\n'),
      },
    ];

    expect(getClaudeCodeCompletedMessageParts(parts)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
        args: { label: 'Work details' },
      },
      { type: 'text', text: 'Ready for the next step.' },
    ]);
  });

  it('keeps an unanswered trailing question visible when the model omits it from the summary', () => {
    const parts: readonly ThreadAssistantMessagePart[] = [
      {
        type: 'text',
        text: [
          'I found three deployed agents.',
          '',
          'Which agent do you want to optimize?',
          STUDIO_MESSAGE_SUMMARY_START,
          'worked_for: 20s',
          'summary: I investigated the available optimization targets.',
          'details_label: worked for 20s',
          STUDIO_MESSAGE_SUMMARY_END,
        ].join('\n'),
      },
    ];

    expect(getClaudeCodeCompletedMessageParts(parts)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
        args: {
          parts: [{ type: 'text', text: 'I found three deployed agents.' }],
        },
      },
      {
        type: 'text',
        text: [
          'I investigated the available optimization targets.',
          '',
          'Which agent do you want to optimize?',
        ].join('\n'),
      },
    ]);
  });

  it('accepts an inline Studio summary block from the model', () => {
    const parts: readonly ThreadAssistantMessagePart[] = [
      { type: 'text', text: 'Detailed work that should be collapsed.' },
      {
        type: 'text',
        text: `${STUDIO_MESSAGE_SUMMARY_START} worked_for: ~3 minutes summary: Analyzed calculator-agent and generated 3 optimization suggestions. Snapshot and suggestions persisted. details_label: worked for ~3 minutes ${STUDIO_MESSAGE_SUMMARY_END}`,
      },
    ];

    expect(getClaudeCodeCompletedMessageParts(parts)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
        args: {
          label: 'worked for ~3 minutes',
          parts: [{ type: 'text', text: 'Detailed work that should be collapsed.' }],
        },
      },
      {
        type: 'text',
        text: 'Analyzed calculator-agent and generated 3 optimization suggestions. Snapshot and suggestions persisted.',
      },
    ]);
  });

  it('preserves markdown formatting in a Studio summary block', () => {
    const markdownSummary = [
      '## Completed',
      '',
      '- Preserved **emphasis**',
      '- Preserved `inline code`',
      '',
      '```ts',
      'const formatted = true;',
      '```',
    ].join('\n');
    const parts: readonly ThreadAssistantMessagePart[] = [
      { type: 'text', text: 'Detailed work that should be collapsed.' },
      {
        type: 'text',
        text: [
          STUDIO_MESSAGE_SUMMARY_START,
          'worked_for: 12s',
          'summary:',
          markdownSummary,
          'details_label: worked for 12s',
          STUDIO_MESSAGE_SUMMARY_END,
        ].join('\n'),
      },
    ];

    expect(getClaudeCodeCompletedMessageParts(parts)).toMatchObject([
      {
        type: 'tool-call',
        toolName: CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
      },
      { type: 'text', text: markdownSummary },
    ]);
  });
});
