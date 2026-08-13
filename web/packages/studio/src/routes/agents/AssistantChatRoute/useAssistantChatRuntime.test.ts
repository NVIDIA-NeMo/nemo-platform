// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAssistantChatRuntime } from '@studio/routes/agents/AssistantChatRoute/useAssistantChatRuntime';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';
import { act, renderHook, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  appendUserMessage: vi.fn(),
  createAssistantSession: vi.fn(),
  invalidateQueries: vi.fn(),
  prepareForUserInput: vi.fn(),
  resolveAssistantInput: vi.fn(),
  resolveAssistantPermission: vi.fn(),
  streamAssistantMessage: vi.fn(),
  submitPrompt: vi.fn(),
}));

vi.mock('@studio/routes/agents/AssistantChatRoute/api', () => ({
  createAssistantSession: mocks.createAssistantSession,
  getAssistantHistorySessionsQueryKey: (workspace: string) => [
    'assistant',
    'history',
    'sessions',
    workspace,
  ],
  resolveAssistantInput: mocks.resolveAssistantInput,
  resolveAssistantPermission: mocks.resolveAssistantPermission,
  streamAssistantMessage: mocks.streamAssistantMessage,
}));

vi.mock('@studio/routes/agents/AssistantChatRoute/useCustomAssistantChatRuntime', () => ({
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

const renderUseAssistantChatRuntime = (options?: Parameters<typeof useAssistantChatRuntime>[0]) =>
  renderHook(() => useAssistantChatRuntime(options));

interface PermissionRequestTestHandlers {
  onPermissionRequest: (request: unknown) => void;
  onDone: () => void;
}

interface InputRequestTestHandlers {
  onInputExpired: (requestId: string) => void;
  onInputRequest: (request: unknown) => void;
  onDone: () => void;
}

describe('useAssistantChatRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: a stream that completes immediately and successfully.
    // Tests that need custom behaviour (permission requests, finishStream, etc.)
    // override this in their own setup.
    mocks.streamAssistantMessage.mockImplementation(
      async ({ handlers }: { handlers: { onDone: () => void } }) => {
        handlers.onDone();
      }
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes the latest streamed assistant model without promoting it to selected model', async () => {
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onAssistantEvent: (event: unknown) => void; onDone: () => void };
      }) => {
        handlers.onAssistantEvent({
          type: 'assistant',
          message: { model: 'claude-sonnet-4-5', content: [] },
        });
        handlers.onAssistantEvent({
          type: 'assistant',
          message: { model: 'claude-sonnet-4-6', content: [] },
        });
        handlers.onDone();
      }
    );

    const { result } = renderUseAssistantChatRuntime();

    await act(async () => {
      await result.current.submitPrompt('List files');
    });

    await waitFor(() => expect(result.current.artifacts.assistant_model).toBe('claude-sonnet-4-6'));
    expect(result.current.artifacts.model).toBeUndefined();
    expect(result.current.artifacts.model_source).toBeUndefined();
  });

  it('passes Studio route context to streamed messages', async () => {
    mocks.createAssistantSession.mockResolvedValue('session-1');

    const { result } = renderUseAssistantChatRuntime({
      studioPathname: '/workspaces/default/jobs?status=running',
      workspace: 'default',
    });

    await act(async () => {
      await result.current.submitPrompt('Show running jobs');
    });

    expect(mocks.streamAssistantMessage).toHaveBeenCalledWith(
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
        useAssistantChatRuntime({
          initialArtifacts: model
            ? {
                assistant_model: model,
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

    await waitFor(() => expect(result.current.artifacts.assistant_model).toBe('claude-sonnet-4-6'));
    expect(result.current.artifacts.model).toBeUndefined();

    rerender({ model: undefined });

    await waitFor(() => expect(result.current.artifacts.assistant_model).toBeUndefined());
  });

  it('pauses for a matching Studio UI suggestion before creating a NeMo Assistant session', async () => {
    let submitPromise!: Promise<void>;
    mockFeatureFlags({ guardrailsEnabled: true });
    mocks.createAssistantSession.mockResolvedValue('session-1');

    const { result } = renderUseAssistantChatRuntime({ workspace: 'default' });

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
    expect(mocks.createAssistantSession).not.toHaveBeenCalled();

    await act(async () => {
      result.current.resolveStudioNavigationRequest('continue');
      await submitPromise;
    });

    expect(mocks.createAssistantSession).toHaveBeenCalledTimes(1);
    expect(result.current.studioNavigationRequest).toBeNull();
  });

  it('does not start Assistant when the user chooses the Studio UI', async () => {
    let submitPromise!: Promise<void>;
    mockFeatureFlags({ guardrailsEnabled: true });

    const { result } = renderUseAssistantChatRuntime({ workspace: 'default' });

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

    expect(mocks.createAssistantSession).not.toHaveBeenCalled();
    expect(mocks.streamAssistantMessage).not.toHaveBeenCalled();
    expect(result.current.studioNavigationRequest).toBeNull();
  });

  it('does not append denial text when permission resolution fails', async () => {
    const onError = vi.fn();
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onPermissionRequest: (request: unknown) => void; onDone: () => void };
      }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'Bash',
          input: { command: 'ls' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
        handlers.onDone();
      }
    );
    mocks.resolveAssistantPermission.mockRejectedValue(new Error('permission failed'));

    const { result } = renderUseAssistantChatRuntime({ onError });

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

    expect(mocks.resolveAssistantPermission).toHaveBeenCalledWith({
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
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onPermissionRequest: (request: unknown) => void; onDone: () => void };
      }) => {
        handlers.onPermissionRequest({
          requestId: 'request-1',
          toolName: 'Bash',
          input: { command: 'ls' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
        handlers.onDone();
      }
    );
    mocks.resolveAssistantPermission.mockResolvedValue(undefined);

    const { result } = renderUseAssistantChatRuntime();

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
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
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
        handlers.onDone();
      }
    );
    mocks.resolveAssistantPermission.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvePermission = resolve;
        })
    );

    const { result } = renderUseAssistantChatRuntime();

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
    // request-2 is queued while request-1 submission is still in-flight
    expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-1' }));

    await act(async () => {
      resolvePermission();
      await resolvePromise;
    });

    // request-1 resolved → request-2 dequeued and now active
    expect(result.current.decisionRequest).toEqual(expect.objectContaining({ id: 'request-2' }));

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('resolves blocking input requests and appends the selected value after success', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onInputRequest: (request: unknown) => void; onDone: () => void };
      }) => {
        handlers.onInputRequest({
          requestId: 'request-1',
          kind: 'agent',
          input: { title: 'Select an agent' },
        });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
        handlers.onDone();
      }
    );
    mocks.resolveAssistantInput.mockResolvedValue(undefined);

    const { result } = renderUseAssistantChatRuntime();

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

    expect(mocks.resolveAssistantInput).toHaveBeenCalledWith({
      sessionId: 'session-1',
      requestId: 'request-1',
      decision: { value: { agent: 'react-agent' } },
    });
    expect(mocks.appendUserMessage).toHaveBeenCalledWith('Selected agent: react-agent');
    expect(result.current.artifacts.selections).toEqual([{ label: 'Agent', value: 'react-agent' }]);
    expect(result.current.artifacts.agent).toBe('react-agent');
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
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
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
        handlers.onDone();
      }
    );
    mocks.resolveAssistantInput.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveInput = resolve;
        })
    );

    const { result } = renderUseAssistantChatRuntime();

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
    // request-2 is queued while request-1 submission is still in-flight
    expect(result.current.inputRequest).toEqual(
      expect.objectContaining({ requestId: 'request-1' })
    );

    await act(async () => {
      resolveInput();
      await resolvePromise;
    });

    // request-1 resolved → request-2 dequeued and now active
    expect(result.current.inputRequest).toEqual(
      expect.objectContaining({ requestId: 'request-2' })
    );

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('discards input resolutions after the request or session becomes stale', async () => {
    let finishStream!: () => void;
    let inputHandlers!: InputRequestTestHandlers;
    let submitPromise!: Promise<void>;
    const resolveInputs: Array<() => void> = [];
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({ handlers }: { handlers: InputRequestTestHandlers }) => {
        inputHandlers = handlers;
        handlers.onInputRequest({ requestId: 'request-1', kind: 'agent', input: {} });
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
        handlers.onDone();
      }
    );
    mocks.resolveAssistantInput.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveInputs.push(resolve);
        })
    );

    const { result } = renderUseAssistantChatRuntime();

    act(() => {
      submitPromise = result.current.submitPrompt('Pick inputs for this workflow');
    });
    await waitFor(() => expect(result.current.inputRequest?.requestId).toBe('request-1'));

    let firstResolution!: Promise<void>;
    act(() => {
      firstResolution = result.current.resolveInputRequest({
        decision: { value: { agent: 'stale-agent' } },
        displayText: 'Selected agent: stale-agent',
      });
    });
    await waitFor(() => expect(result.current.inputStatus).toBe('submitting'));

    act(() => {
      inputHandlers.onInputRequest({ requestId: 'request-2', kind: 'model', input: {} });
      inputHandlers.onInputExpired('request-1');
    });
    expect(result.current.inputRequest?.requestId).toBe('request-2');

    await act(async () => {
      resolveInputs[0]?.();
      await firstResolution;
    });

    expect(result.current.artifacts.selections).toEqual([]);
    expect(mocks.appendUserMessage).not.toHaveBeenCalled();
    expect(result.current.inputRequest?.requestId).toBe('request-2');

    let secondResolution!: Promise<void>;
    act(() => {
      secondResolution = result.current.resolveInputRequest({
        decision: { value: { model: 'stale-model' } },
        displayText: 'Selected model: stale-model',
      });
    });
    await waitFor(() => expect(result.current.inputStatus).toBe('submitting'));

    act(() => {
      result.current.loadSession({
        artifacts: {
          selections: [{ label: 'Environment', value: 'production' }],
          files: [],
          links: [],
          jobs: [],
          tools: [],
        },
        messages: [],
        sessionId: 'session-2',
      });
    });

    await act(async () => {
      resolveInputs[1]?.();
      await secondResolution;
    });

    expect(result.current.artifacts.selections).toEqual([
      { label: 'Environment', value: 'production' },
    ]);
    expect(mocks.appendUserMessage).not.toHaveBeenCalled();
    expect(result.current.inputRequest).toBeNull();

    await act(async () => {
      finishStream();
      await submitPromise;
    });
  });

  it('extracts AskUserQuestion requests into question choices', async () => {
    let finishStream!: () => void;
    let submitPromise!: Promise<void>;
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onPermissionRequest: (request: unknown) => void; onDone: () => void };
      }) => {
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
        handlers.onDone();
      }
    );
    mocks.resolveAssistantPermission.mockResolvedValue(undefined);

    const { result } = renderUseAssistantChatRuntime();

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

    expect(mocks.resolveAssistantPermission).toHaveBeenCalledWith({
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
    mocks.createAssistantSession.mockResolvedValue('session-1');
    mocks.streamAssistantMessage.mockImplementation(
      async ({
        handlers,
      }: {
        handlers: { onPermissionRequest: (request: unknown) => void; onDone: () => void };
      }) => {
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
        handlers.onDone();
      }
    );
    mocks.resolveAssistantPermission.mockResolvedValue(undefined);

    const { result } = renderUseAssistantChatRuntime();

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

    expect(mocks.resolveAssistantPermission).toHaveBeenCalledWith({
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
