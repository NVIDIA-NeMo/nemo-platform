// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { act, renderHook, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  appendUserMessage: vi.fn(),
  createClaudeCodeSession: vi.fn(),
  invalidateQueries: vi.fn(),
  resolveClaudeCodePermission: vi.fn(),
  streamClaudeCodeMessage: vi.fn(),
  submitPrompt: vi.fn(),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/api', () => ({
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY: ['claude-code', 'history', 'sessions'],
  createClaudeCodeSession: mocks.createClaudeCodeSession,
  resolveClaudeCodePermission: mocks.resolveClaudeCodePermission,
  streamClaudeCodeMessage: mocks.streamClaudeCodeMessage,
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime', () => ({
  useCustomAssistantChatRuntime: ({
    onRun,
  }: {
    onRun: (context: unknown) => Promise<unknown>;
  }) => ({
    appendUserMessage: mocks.appendUserMessage,
    handleReset: vi.fn(),
    isRunning: false,
    runtime: {},
    submitPrompt: async (prompt: string) => {
      await onRun({
        prompt,
        signal: new AbortController().signal,
        appendAssistantText: vi.fn(),
        prepareForUserInput: vi.fn(),
        isCurrentRun: () => true,
      });
      await mocks.submitPrompt(prompt);
    },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: mocks.invalidateQueries,
  }),
}));

const renderUseClaudeCodeChatRuntime = (options?: Parameters<typeof useClaudeCodeChatRuntime>[0]) =>
  renderHook(() => useClaudeCodeChatRuntime(options));

describe('useClaudeCodeChatRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not append denial text when permission resolution fails', async () => {
    const onError = vi.fn();
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onPermissionRequest: (request: unknown) => void } }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'Bash',
          input: { command: 'ls' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodePermission.mockRejectedValue(new Error('permission failed'));

    const { result } = renderUseClaudeCodeChatRuntime({ onError });

    act(() => {
      submitPromise = result.current.submitPrompt('List files');
    });
    await waitFor(() =>
      expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-1' }))
    );

    await act(async () => {
      await result.current.resolveDecisionRequest(result.current.decisionChoices[2], {
        text: 'Use rg instead',
      });
    });

    expect(mocks.resolveClaudeCodePermission).toHaveBeenCalledWith({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: {
        approved: false,
        reason: 'Use rg instead',
      },
    });
    expect(mocks.appendUserMessage).not.toHaveBeenCalled();
    expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-1' }));
    expect(result.current.decisionStatus).toBe('pending');
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'permission failed' }));

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('appends denial text only after permission resolution succeeds', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onPermissionRequest: (request: unknown) => void } }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'Bash',
          input: { command: 'ls' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodePermission.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('List files');
    });
    await waitFor(() =>
      expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-1' }))
    );

    await act(async () => {
      await result.current.resolveDecisionRequest(result.current.decisionChoices[2], {
        text: 'Use rg instead',
      });
    });

    expect(mocks.appendUserMessage).toHaveBeenCalledWith('Use rg instead');
    expect(result.current.decisionRequest).toBeNull();

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('extracts AskUserQuestion requests into question choices', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onPermissionRequest: (request: unknown) => void } }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'AskUserQuestion',
          input: {
            questions: [
              {
                question:
                  'Should the agent only handle Trinidad and Tobago time, or also support related questions?',
                header: 'Timezone scope',
                multiSelect: false,
                options: [
                  {
                    label: 'Only Trinidad and Tobago time',
                    description: 'Keep the agent focused on one timezone.',
                  },
                  {
                    label: 'Support related questions',
                    description: 'Allow neighboring timezone and scheduling questions too.',
                  },
                ],
              },
            ],
          },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodePermission.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('Build a timezone agent');
    });
    await waitFor(() =>
      expect(result.current.decisionRequest).toEqual(
        expect.objectContaining({
          title: 'Timezone scope',
          description:
            'Should the agent only handle Trinidad and Tobago time, or also support related questions?',
        })
      )
    );

    expect(result.current.decisionChoices).toEqual([
      {
        id: 'answer-0',
        label: 'Only Trinidad and Tobago time',
        description: 'Keep the agent focused on one timezone.',
      },
      {
        id: 'answer-1',
        label: 'Support related questions',
        description: 'Allow neighboring timezone and scheduling questions too.',
      },
      {
        id: 'answer-custom',
        label: 'No, and tell the Agent what to do',
        input: {
          ariaLabel: 'Tell the Agent what to do',
          placeholder: 'Tell the Agent what to do',
        },
      },
    ]);

    await act(async () => {
      await result.current.resolveDecisionRequest(result.current.decisionChoices[1]);
    });

    expect(mocks.resolveClaudeCodePermission).toHaveBeenCalledWith({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: {
        approved: false,
        reason:
          'Your question has been answered: "Should the agent only handle Trinidad and Tobago time, or also support related questions?"="Support related questions". You can now continue with this answer in mind.',
      },
    });
    expect(mocks.appendUserMessage).toHaveBeenCalledWith(
      [
        'Should the agent only handle Trinidad and Tobago time, or also support related questions?',
        'Support related questions',
      ].join('\n')
    );

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('submits the fixed AskUserQuestion custom instruction option', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onPermissionRequest: (request: unknown) => void } }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'AskUserQuestion',
          input: {
            questions: [
              {
                question: 'Should the agent only handle Trinidad and Tobago time?',
                header: 'Timezone scope',
                options: [
                  {
                    label: 'Yes, only Trinidad and Tobago time',
                  },
                ],
              },
            ],
          },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodePermission.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('Build a timezone agent');
    });
    await waitFor(() =>
      expect(result.current.decisionChoices).toContainEqual(
        expect.objectContaining({ id: 'answer-custom' })
      )
    );

    const customChoice = result.current.decisionChoices.find(
      (choice) => choice.id === 'answer-custom'
    );
    if (!customChoice) {
      throw new Error('Expected custom AskUserQuestion choice');
    }

    await act(async () => {
      await result.current.resolveDecisionRequest(customChoice, {
        text: 'Support Caribbean timezones too',
      });
    });

    expect(mocks.resolveClaudeCodePermission).toHaveBeenCalledWith({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: {
        approved: false,
        reason:
          'Your question has been answered: "Should the agent only handle Trinidad and Tobago time?"="Support Caribbean timezones too". You can now continue with this answer in mind.',
      },
    });
    expect(mocks.appendUserMessage).toHaveBeenCalledWith(
      [
        'Should the agent only handle Trinidad and Tobago time?',
        'Support Caribbean timezones too',
      ].join('\n')
    );

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });
});
