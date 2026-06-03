// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import { getMessageText } from '@nemo/common/src/components/AssistantChat/messageUtils';
import {
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

describe('useCustomAssistantChatRuntime', () => {
  beforeEach(() => {
    mocks.useExternalStoreRuntime.mockClear();
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
});
