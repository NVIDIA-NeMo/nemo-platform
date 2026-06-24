// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';
import { act, renderHook, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  appendUserMessage: vi.fn(),
  createClaudeCodeSession: vi.fn(),
  invalidateQueries: vi.fn(),
  prepareForUserInput: vi.fn(),
  resolveClaudeCodeInput: vi.fn(),
  resolveClaudeCodePermission: vi.fn(),
  streamClaudeCodeMessage: vi.fn(),
  submitPrompt: vi.fn(),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/api', () => ({
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY: ['claude-code', 'history', 'sessions'],
  createClaudeCodeSession: mocks.createClaudeCodeSession,
  resolveClaudeCodeInput: mocks.resolveClaudeCodeInput,
  resolveClaudeCodePermission: mocks.resolveClaudeCodePermission,
  streamClaudeCodeMessage: mocks.streamClaudeCodeMessage,
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime', () => ({
  useCustomAssistantChatRuntime: ({
    onBeforeRun,
    onRun,
  }: {
    onBeforeRun?: (context: unknown) => Promise<'continue' | 'cancel' | void>;
    onRun: (context: unknown) => Promise<unknown>;
  }) => ({
    appendUserMessage: mocks.appendUserMessage,
    handleReset: vi.fn(),
    isRunning: false,
    messages: [],
    replaceMessages: vi.fn(),
    runtime: {},
    submitPrompt: async (prompt: string) => {
      const context = {
        prompt,
        signal: new AbortController().signal,
        appendAssistantParts: vi.fn(),
        appendAssistantText: vi.fn(),
        prepareForUserInput: mocks.prepareForUserInput,
        isCurrentRun: () => true,
      };
      const beforeRunResult = await onBeforeRun?.(context);
      if (beforeRunResult !== 'cancel') {
        await onRun(context);
      }
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

interface PermissionRequestTestHandlers {
  onPermissionRequest: (request: unknown) => void;
}

interface InputRequestTestHandlers {
  onInputRequest: (request: unknown) => void;
}

describe('useClaudeCodeChatRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes the latest streamed coding-agent model without promoting it to selected model', async () => {
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onClaudeEvent: (event: unknown) => void } }) => {
        handlers.onClaudeEvent({
          type: 'assistant',
          message: { model: 'claude-sonnet-4-5', content: [] },
        });
        handlers.onClaudeEvent({
          type: 'assistant',
          message: { model: 'claude-sonnet-4-6', content: [] },
        });
      }
    );

    const { result } = renderUseClaudeCodeChatRuntime();

    await act(async () => {
      await result.current.submitPrompt('List files');
    });

    await waitFor(() =>
      expect(result.current.artifacts.coding_agent_model).toBe('claude-sonnet-4-6')
    );
    expect(result.current.artifacts.model).toBeUndefined();
    expect(result.current.artifacts.model_source).toBeUndefined();
  });

  it('passes Studio route context to streamed messages', async () => {
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime({
      studioPathname: '/workspaces/default/jobs?status=running',
      workspace: 'default',
    });

    await act(async () => {
      await result.current.submitPrompt('Show running jobs');
    });

    expect(mocks.streamClaudeCodeMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Show running jobs',
        sessionId: 'session-1',
        studioPathname: '/workspaces/default/jobs?status=running',
        workspace: 'default',
      })
    );
  });

  it('syncs artifacts when historical session metadata arrives after mount', async () => {
    const { rerender, result } = renderHook(
      ({ model }: { model?: string }) =>
        useClaudeCodeChatRuntime({
          initialArtifacts: model
            ? {
                coding_agent_model: model,
                selections: [],
                files: [],
                links: [],
                jobs: [],
                tools: [],
              }
            : undefined,
        }),
      { initialProps: {} }
    );

    expect(result.current.artifacts.model).toBeUndefined();

    rerender({ model: 'claude-sonnet-4-6' });

    await waitFor(() =>
      expect(result.current.artifacts.coding_agent_model).toBe('claude-sonnet-4-6')
    );
    expect(result.current.artifacts.model).toBeUndefined();

    rerender({ model: undefined });

    await waitFor(() => expect(result.current.artifacts.coding_agent_model).toBeUndefined());
  });

  it('pauses for a matching Studio UI suggestion before creating a Claude Code session', async () => {
    let submitPromise!: Promise<void>;
    mockFeatureFlags({ guardrailsEnabled: true });
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime({ workspace: 'default' });

    act(() => {
      submitPromise = result.current.submitPrompt('Add guardrails to an agent');
    });

    await waitFor(() =>
      expect(result.current.studioNavigationRequest).toEqual(
        expect.objectContaining({
          prompt: 'Add guardrails to an agent',
          suggestion: expect.objectContaining({
            id: 'guardrails',
            href: '/workspaces/default/guardrails',
          }),
        })
      )
    );

    expect(mocks.prepareForUserInput).toHaveBeenCalled();
    expect(mocks.createClaudeCodeSession).not.toHaveBeenCalled();

    await act(async () => {
      result.current.resolveStudioNavigationRequest('continue');
      await submitPromise;
    });

    expect(mocks.createClaudeCodeSession).toHaveBeenCalledTimes(1);
    expect(result.current.studioNavigationRequest).toBeNull();
  });

  it('does not start Claude Code when the user chooses the Studio UI', async () => {
    let submitPromise!: Promise<void>;
    mockFeatureFlags({ guardrailsEnabled: true });

    const { result } = renderUseClaudeCodeChatRuntime({ workspace: 'default' });

    act(() => {
      submitPromise = result.current.submitPrompt('Add guardrails to an agent');
    });

    await waitFor(() =>
      expect(result.current.studioNavigationRequest?.suggestion.id).toBe('guardrails')
    );

    await act(async () => {
      result.current.resolveStudioNavigationRequest('navigate');
      await submitPromise;
    });

    expect(mocks.createClaudeCodeSession).not.toHaveBeenCalled();
    expect(mocks.streamClaudeCodeMessage).not.toHaveBeenCalled();
    expect(result.current.studioNavigationRequest).toBeNull();
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

  it('does not clear a newer permission request when an older permission resolution completes', async () => {
    let finishStream!: () => void;
    let permissionHandlers!: PermissionRequestTestHandlers;
    let resolvePermission!: () => void;
    let resolvePromise!: Promise<void>;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: PermissionRequestTestHandlers }) => {
        permissionHandlers = handlers;
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
    mocks.resolveClaudeCodePermission.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvePermission = resolve;
        })
    );

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('List files');
    });
    await waitFor(() =>
      expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-1' }))
    );

    act(() => {
      resolvePromise = result.current.resolveDecisionRequest(result.current.decisionChoices[0]);
    });
    await waitFor(() => expect(result.current.decisionStatus).toBe('submitting'));

    act(() => {
      permissionHandlers.onPermissionRequest({
        requestId: 'request-2',
        toolName: 'Bash',
        input: { command: 'pwd' },
      });
    });
    expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-2' }));

    await act(async () => {
      resolvePermission();
      await resolvePromise;
    });

    expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-2' }));

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('resolves blocking input requests and appends the selected value after success', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: { onInputRequest: (request: unknown) => void } }) => {
        handlers.onInputRequest({
          requestId: 'request-1',
          kind: 'agent',
          input: { title: 'Select an agent' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodeInput.mockResolvedValue(undefined);

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('Pick an agent for this workflow');
    });
    await waitFor(() =>
      expect(result.current.inputRequest).toEqual(
        expect.objectContaining({
          requestId: 'request-1',
          kind: 'agent',
        })
      )
    );

    await act(async () => {
      await result.current.resolveInputRequest({
        decision: { value: { agent: 'react-agent' } },
        displayText: 'Selected agent: react-agent',
      });
    });

    expect(mocks.resolveClaudeCodeInput).toHaveBeenCalledWith({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: { value: { agent: 'react-agent' } },
    });
    expect(mocks.appendUserMessage).toHaveBeenCalledWith('Selected agent: react-agent');
    expect(result.current.inputRequest).toBeNull();

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('does not clear a newer input request when an older input resolution completes', async () => {
    let finishStream!: () => void;
    let inputHandlers!: InputRequestTestHandlers;
    let resolveInput!: () => void;
    let resolvePromise!: Promise<void>;
    let submitPromise!: Promise<void>;
    mocks.createClaudeCodeSession.mockResolvedValue('session-1');
    mocks.streamClaudeCodeMessage.mockImplementation(
      async ({ handlers }: { handlers: InputRequestTestHandlers }) => {
        inputHandlers = handlers;
        handlers.onInputRequest({
          requestId: 'request-1',
          kind: 'agent',
          input: { title: 'Select an agent' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
      }
    );
    mocks.resolveClaudeCodeInput.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveInput = resolve;
        })
    );

    const { result } = renderUseClaudeCodeChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('Pick an agent for this workflow');
    });
    await waitFor(() =>
      expect(result.current.inputRequest).toEqual(
        expect.objectContaining({ requestId: 'request-1' })
      )
    );

    act(() => {
      resolvePromise = result.current.resolveInputRequest({
        decision: { value: { agent: 'react-agent' } },
        displayText: 'Selected agent: react-agent',
      });
    });
    await waitFor(() => expect(result.current.inputStatus).toBe('submitting'));

    act(() => {
      inputHandlers.onInputRequest({
        requestId: 'request-2',
        kind: 'dataset_file',
        input: { title: 'Select a dataset' },
      });
    });
    expect(result.current.inputRequest).toEqual(
      expect.objectContaining({ requestId: 'request-2' })
    );

    await act(async () => {
      resolveInput();
      await resolvePromise;
    });

    expect(result.current.inputRequest).toEqual(
      expect.objectContaining({ requestId: 'request-2' })
    );

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
