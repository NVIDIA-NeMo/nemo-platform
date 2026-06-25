// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart, ThreadMessageLike } from '@assistant-ui/react';
import { getMessageText } from '@nemo/common/src/components/AssistantChat/messageUtils';
import {
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import {
  type CustomAssistantBeforeRunContext,
  type CustomAssistantRunContext,
  useCustomAssistantChatRuntime,
} from '@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime';
import { act, renderHook, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  useExternalStoreRuntime: vi.fn((runtime: unknown) => runtime),
}));

vi.mock('@assistant-ui/react', () => ({
  useExternalStoreRuntime: mocks.useExternalStoreRuntime,
}));

interface MockRuntime {
  messages: readonly ThreadMessageLike[];
  onCancel: () => Promise<void>;
}

const getMockRuntime = (runtime: unknown): MockRuntime => {
  if (typeof runtime !== 'object' || runtime === null || !('messages' in runtime)) {
    throw new Error('Expected mocked assistant runtime');
  }

  return runtime as MockRuntime;
};

const getAssistantContent = (messages: readonly ThreadMessageLike[]) => {
  const content = messages[1]?.content;
  if (!Array.isArray(content)) throw new Error('Expected assistant content parts');
  return content;
};

describe('useCustomAssistantChatRuntime', () => {
  beforeEach(() => {
    mocks.useExternalStoreRuntime.mockClear();
  });

  it('pauses before running and resumes when the before-run hook continues', async () => {
    let continueRun!: () => void;
    const onBeforeRun = vi.fn(async (context: CustomAssistantBeforeRunContext) => {
      context.prepareForUserInput();
      await new Promise<void>((resolve) => {
        continueRun = resolve;
      });
      return 'continue' as const;
    });
    const onRun = vi.fn(async (context: CustomAssistantRunContext) => {
      context.appendAssistantText('Continuing in chat.');
    });
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onBeforeRun, onRun }));

    act(() => {
      void result.current.submitPrompt('Add guardrails');
    });

    await waitFor(() => {
      expect(onBeforeRun).toHaveBeenCalledWith(
        expect.objectContaining({ prompt: 'Add guardrails' })
      );
      expect(onRun).not.toHaveBeenCalled();
      expect(getMockRuntime(result.current.runtime).messages.map(getMessageText)).toEqual([
        'Add guardrails',
      ]);
    });

    await act(async () => {
      continueRun();
    });

    await waitFor(() => {
      expect(onRun).toHaveBeenCalled();
      expect(getMockRuntime(result.current.runtime).messages.map(getMessageText)).toEqual([
        'Add guardrails',
        'Continuing in chat.',
      ]);
    });
  });

  it('does not run when the before-run hook cancels', async () => {
    const onBeforeRun = vi.fn((context: CustomAssistantBeforeRunContext) => {
      context.prepareForUserInput();
      return 'cancel' as const;
    });
    const onRun = vi.fn();
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onBeforeRun, onRun }));

    await act(async () => {
      await result.current.submitPrompt('Open guardrails');
    });

    expect(onRun).not.toHaveBeenCalled();
    expect(getMockRuntime(result.current.runtime).messages.map(getMessageText)).toEqual([
      'Open guardrails',
    ]);
  });

  it('shows user interventions between agent messages', async () => {
    let runContext: CustomAssistantRunContext | undefined;
    const onRun = vi.fn(async (context: CustomAssistantRunContext) => {
      runContext = context;
      await new Promise<void>((resolve) => {
        context.signal.addEventListener('abort', () => resolve(), { once: true });
      });
    });
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onRun }));

    act(() => {
      void result.current.submitPrompt('List files');
    });

    await waitFor(() => {
      const runtime = getMockRuntime(result.current.runtime);
      expect(runtime.messages).toHaveLength(2);
      expect(runtime.messages[1]?.role).toBe('assistant');
      expect(runtime.messages[1]?.status?.type).toBe('running');
    });

    act(() => {
      runContext?.appendAssistantText('I need approval first.');
    });

    await waitFor(() => {
      const runtime = getMockRuntime(result.current.runtime);
      expect(runtime.messages.map(getMessageText)).toEqual([
        'List files',
        'I need approval first.',
      ]);
    });

    act(() => {
      runContext?.prepareForUserInput();
      result.current.appendUserMessage('Use rg instead');
      runContext?.appendAssistantText('Using rg instead.');
    });

    await waitFor(() => {
      const runtime = getMockRuntime(result.current.runtime);
      expect(runtime.messages.map((message) => message.role)).toEqual([
        'user',
        'assistant',
        'user',
        'assistant',
      ]);
      expect(runtime.messages.map(getMessageText)).toEqual([
        'List files',
        'I need approval first.',
        'Use rg instead',
        'Using rg instead.',
      ]);
    });

    await act(async () => {
      await getMockRuntime(result.current.runtime).onCancel();
    });
  });

  it('combines consecutive subtle tool calls across streamed appends', async () => {
    let runContext: CustomAssistantRunContext | undefined;
    const onRun = vi.fn(async (context: CustomAssistantRunContext) => {
      runContext = context;
      await new Promise<void>((resolve) => {
        context.signal.addEventListener('abort', () => resolve(), { once: true });
      });
    });
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onRun }));

    act(() => {
      void result.current.submitPrompt('Check files');
    });

    await waitFor(() => {
      expect(getMockRuntime(result.current.runtime).messages).toHaveLength(2);
    });

    const bashPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_bash',
      toolName: 'Bash',
      args: { command: 'pwd' },
      argsText: '{"command":"pwd"}',
    };
    const readPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_read',
      toolName: 'Read',
      args: { file_path: 'README.md' },
      argsText: '{"file_path":"README.md"}',
    };

    act(() => {
      runContext?.appendAssistantParts([bashPart]);
    });

    await waitFor(() => {
      const content = getAssistantContent(getMockRuntime(result.current.runtime).messages);
      expect(content).toEqual([bashPart]);
    });

    act(() => {
      runContext?.appendAssistantParts([readPart]);
    });

    await waitFor(() => {
      const content = getAssistantContent(getMockRuntime(result.current.runtime).messages);
      expect(content).toHaveLength(1);
      expect(content[0]).toMatchObject({
        type: 'tool-call',
        toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
        args: {
          actions: [
            { args: { command: 'pwd' }, toolCallId: 'toolu_bash', toolName: 'Bash' },
            { args: { file_path: 'README.md' }, toolCallId: 'toolu_read', toolName: 'Read' },
          ],
        },
      });
    });

    await act(async () => {
      await getMockRuntime(result.current.runtime).onCancel();
    });
  });

  it('does not collapse agent thinking while waiting for user input', async () => {
    const bashPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_bash',
      toolName: 'Bash',
      args: { command: 'pwd' },
      argsText: '{"command":"pwd"}',
    };
    let runContext: CustomAssistantRunContext | undefined;
    const onRun = vi.fn(async (context: CustomAssistantRunContext) => {
      runContext = context;
      context.appendAssistantParts([{ type: 'text', text: 'I will inspect the repo first.' }]);
      context.appendAssistantParts([bashPart]);
      context.prepareForUserInput();
      await new Promise<void>((resolve) => {
        context.signal.addEventListener('abort', () => resolve(), { once: true });
      });
    });
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onRun }));

    act(() => {
      void result.current.submitPrompt('Check files');
    });

    await waitFor(() => {
      expect(runContext).toBeDefined();
      const content = getAssistantContent(getMockRuntime(result.current.runtime).messages);
      expect(content).toEqual([{ type: 'text', text: 'I will inspect the repo first.' }, bashPart]);
      expect(getMockRuntime(result.current.runtime).messages[1]?.status).toEqual({
        type: 'complete',
        reason: 'stop',
      });
    });

    await act(async () => {
      await getMockRuntime(result.current.runtime).onCancel();
    });
  });

  it('keeps completed tool activity before the final summary', async () => {
    const bashPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_bash',
      toolName: 'Bash',
      args: { command: 'pwd' },
      argsText: '{"command":"pwd"}',
    };
    const readPart: ThreadAssistantMessagePart = {
      type: 'tool-call',
      toolCallId: 'toolu_read',
      toolName: 'Read',
      args: { file_path: 'README.md' },
      argsText: '{"file_path":"README.md"}',
    };
    let runContext: CustomAssistantRunContext | undefined;
    let finishRun!: () => void;
    const onRun = vi.fn(async (context: CustomAssistantRunContext) => {
      runContext = context;
      context.appendAssistantParts([
        { type: 'text', text: 'I will inspect the repo first.' },
        bashPart,
      ]);
      await new Promise<void>((resolve) => {
        finishRun = resolve;
      });
      context.appendAssistantParts([
        readPart,
        {
          type: 'text',
          text: 'I found the relevant files.\n\nI checked the repo.\n\nTests passed.',
        },
      ]);
    });
    const { result } = renderHook(() => useCustomAssistantChatRuntime({ onRun }));

    act(() => {
      void result.current.submitPrompt('Check files');
    });

    await waitFor(() => {
      expect(runContext).toBeDefined();
      const content = getAssistantContent(getMockRuntime(result.current.runtime).messages);
      expect(content).toEqual([{ type: 'text', text: 'I will inspect the repo first.' }, bashPart]);
    });

    await act(async () => {
      finishRun();
    });

    await waitFor(() => {
      const content = getAssistantContent(getMockRuntime(result.current.runtime).messages);
      expect(content).toMatchObject([
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
          args: {
            text: 'I will inspect the repo first.\n\nI found the relevant files.',
          },
        },
        {
          type: 'tool-call',
          toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
          args: {
            actions: [
              { toolName: 'Bash', args: { command: 'pwd' } },
              { toolName: 'Read', args: { file_path: 'README.md' } },
            ],
          },
        },
        { type: 'text', text: 'I checked the repo.\n\nTests passed.' },
      ]);
      expect(getMockRuntime(result.current.runtime).messages[1]?.status).toEqual({
        type: 'complete',
        reason: 'stop',
      });
    });
  });
});
