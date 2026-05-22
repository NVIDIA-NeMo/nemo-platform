// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantChat } from '@nemo/common/src/components/AssistantChat';
import type { StudioTool } from '@nemo/common/src/components/AssistantChat/tools';
import {
  ThemeProvider as KaizenThemeProvider,
  TooltipProvider,
} from '@nvidia/foundations-react-core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ChatCompletion, ChatCompletionChunk } from 'openai/resources/index.mjs';
import type { Stream } from 'openai/streaming.mjs';
import type { ReactElement } from 'react';

const mocks = vi.hoisted(() => ({
  createChatCompletion: vi.fn(),
}));

vi.mock('@nemo/common/src/hooks/useChatCompletion', () => ({
  useChatCompletion: () => ({
    mutateAsync: mocks.createChatCompletion,
  }),
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => ({ user: undefined }),
}));

const createCompletion = (content: string): ChatCompletion => ({
  id: 'completion-id',
  object: 'chat.completion',
  created: 1740419165,
  model: 'test-model',
  choices: [
    {
      index: 0,
      message: {
        role: 'assistant',
        content,
        refusal: null,
      },
      finish_reason: 'stop',
      logprobs: null,
    },
  ],
});

const createCompletionChunk = (content: string): ChatCompletionChunk => ({
  id: 'completion-id',
  object: 'chat.completion.chunk',
  created: 1740419165,
  model: 'test-model',
  choices: [
    {
      index: 0,
      delta: content ? { content } : {},
      finish_reason: null,
      logprobs: null,
    },
  ],
});

const createHangingStream = (content: string): Stream<ChatCompletionChunk> => {
  const controller = new AbortController();
  const waitForAbort = () =>
    new Promise<void>((resolve) => {
      if (controller.signal.aborted) {
        resolve();
        return;
      }

      controller.signal.addEventListener('abort', () => resolve(), { once: true });
    });

  return {
    controller,
    async *[Symbol.asyncIterator]() {
      yield createCompletionChunk(content);
      await waitForAbort();
    },
  } as unknown as Stream<ChatCompletionChunk>;
};

const completion = createCompletion('Hello from inference gateway.');

interface CompletionRequestWithSignal {
  signal?: AbortSignal;
}

const renderAssistantChat = (element: ReactElement) =>
  render(
    <KaizenThemeProvider className="h-full" density="standard" theme="light">
      <TooltipProvider>{element}</TooltipProvider>
    </KaizenThemeProvider>
  );

describe('AssistantChat', () => {
  beforeEach(() => {
    mocks.createChatCompletion.mockReset();
    mocks.createChatCompletion.mockResolvedValue(completion);
  });

  it('sends text prompts through useChatCompletion', async () => {
    renderAssistantChat(<AssistantChat model="test-model" workspace="default" />);

    await userEvent.type(screen.getByRole('textbox', { name: /Task prompt/i }), 'Hello model');
    await userEvent.click(screen.getByRole('button', { name: /Submit/i }));

    expect(await screen.findByText('Hello from inference gateway.')).toBeInTheDocument();
    expect(screen.getByText('Hello model')).toBeInTheDocument();

    await waitFor(() =>
      expect(mocks.createChatCompletion).toHaveBeenCalledWith(
        expect.objectContaining({
          model: 'test-model',
          workspace: 'default',
          stream: true,
          messages: [{ role: 'user', content: 'Hello model' }],
        })
      )
    );
  });

  it('clears the current thread', async () => {
    renderAssistantChat(
      <AssistantChat
        model="test-model"
        initialMessages={[
          {
            role: 'user',
            content: [{ type: 'text', text: 'Existing message' }],
          },
        ]}
      />
    );

    expect(screen.getByText('Existing message')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Reset/i }));

    expect(screen.queryByText('Existing message')).not.toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('edits a user message and re-runs inference with the edited prompt', async () => {
    mocks.createChatCompletion
      .mockResolvedValueOnce(createCompletion('Original response.'))
      .mockResolvedValueOnce(createCompletion('Edited response.'));

    renderAssistantChat(<AssistantChat model="test-model" workspace="default" />);

    await userEvent.type(screen.getByRole('textbox', { name: /Task prompt/i }), 'Original prompt');
    await userEvent.click(screen.getByRole('button', { name: /Submit/i }));

    expect(await screen.findByText('Original response.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Edit message/i }));
    const editInput = screen.getByRole('textbox', { name: /Edit message/i });
    expect(editInput).toHaveValue('Original prompt');
    expect(editInput.tagName).toBe('TEXTAREA');

    await userEvent.clear(editInput);
    await userEvent.type(editInput, 'Edited prompt');
    await userEvent.click(screen.getByRole('button', { name: /Save edit/i }));

    expect(await screen.findByText('Edited response.')).toBeInTheDocument();
    expect(screen.getByText('Edited prompt')).toBeInTheDocument();
    expect(screen.queryByText('Original prompt')).not.toBeInTheDocument();
    expect(screen.queryByText('Original response.')).not.toBeInTheDocument();

    await waitFor(() => expect(mocks.createChatCompletion).toHaveBeenCalledTimes(2));
    expect(mocks.createChatCompletion).toHaveBeenLastCalledWith(
      expect.objectContaining({
        model: 'test-model',
        workspace: 'default',
        stream: true,
        messages: [{ role: 'user', content: 'Edited prompt' }],
      })
    );
  });

  it('stops a hanging stream when stop is clicked', async () => {
    const stream = createHangingStream('0 this is an example response');
    const abortSpy = vi.spyOn(stream.controller, 'abort');
    mocks.createChatCompletion.mockResolvedValueOnce(stream);

    renderAssistantChat(<AssistantChat model="test-model" workspace="default" />);

    await userEvent.type(screen.getByRole('textbox', { name: /Task prompt/i }), 'Hang forever');
    await userEvent.click(screen.getByRole('button', { name: /Submit/i }));

    expect(await screen.findByText('0 this is an example response')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Stop/i })).toBeEnabled();

    await userEvent.click(screen.getByRole('button', { name: /Stop/i }));

    await waitFor(() => expect(abortSpy).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Stop/i })).not.toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /Submit/i })).toBeInTheDocument();
    expect(screen.getByText('0 this is an example response')).toBeInTheDocument();
  });

  it('executes a registered studio tool and feeds the result back into a second completion', async () => {
    const execute = vi.fn<
      (args: Record<string, unknown>) => Promise<{ ok: true; result: { ack: string } }>
    >(async () => ({ ok: true, result: { ack: 'ok' } }));
    const testTool: StudioTool = {
      name: 'echo_tool',
      label: 'Echo',
      description: 'Echo back arguments.',
      parameters: { type: 'object', properties: {}, additionalProperties: true },
      execute,
    };
    const toolCallCompletion: ChatCompletion = {
      id: 'completion-tool',
      object: 'chat.completion',
      created: 1,
      model: 'test-model',
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: '',
            refusal: null,
            tool_calls: [
              {
                id: 'call_echo_1',
                type: 'function',
                function: { name: 'echo_tool', arguments: '{"value":42}' },
              },
            ],
          },
          finish_reason: 'tool_calls',
          logprobs: null,
        },
      ],
    };
    const secondStream: Stream<ChatCompletionChunk> = {
      controller: new AbortController(),

      async *[Symbol.asyncIterator]() {
        yield createCompletionChunk('Echoed back the value.');
        yield {
          id: 'c2',
          object: 'chat.completion.chunk',
          created: 1,
          model: 'test-model',
          choices: [{ index: 0, delta: {}, finish_reason: 'stop', logprobs: null }],
        } as ChatCompletionChunk;
      },
    } as unknown as Stream<ChatCompletionChunk>;

    mocks.createChatCompletion
      .mockResolvedValueOnce(toolCallCompletion)
      .mockResolvedValueOnce(secondStream);

    renderAssistantChat(
      <AssistantChat
        model="test-model"
        workspace="default"
        tools={[testTool]}
        defaultEnabledTools={['echo_tool']}
      />
    );

    await userEvent.type(screen.getByRole('textbox', { name: /Task prompt/i }), 'echo please');
    await userEvent.click(screen.getByRole('button', { name: /Submit/i }));

    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    expect(execute.mock.calls[0][0]).toEqual({ value: 42 });

    expect(await screen.findByText('Echoed back the value.')).toBeInTheDocument();
    await waitFor(() => expect(mocks.createChatCompletion).toHaveBeenCalledTimes(2));

    const secondCall = mocks.createChatCompletion.mock.calls[1][0];
    expect(secondCall.messages).toEqual([
      { role: 'user', content: 'echo please' },
      {
        role: 'assistant',
        content: null,
        tool_calls: [
          {
            id: 'call_echo_1',
            type: 'function',
            function: { name: 'echo_tool', arguments: '{"value":42}' },
          },
        ],
      },
      { role: 'tool', tool_call_id: 'call_echo_1', content: '{"ack":"ok"}' },
    ]);
    // Tool definitions are not re-advertised after a tool result, forcing the
    // follow-up round to produce a final assistant response.
    expect(secondCall.tools).toBeUndefined();
  });

  it('aborts a pending completion request when stop is clicked', async () => {
    let requestSignal: AbortSignal | undefined;
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';

    mocks.createChatCompletion.mockImplementationOnce((request: CompletionRequestWithSignal) => {
      requestSignal = request.signal;

      return new Promise<ChatCompletion>((_resolve, reject) => {
        request.signal?.addEventListener('abort', () => reject(abortError), { once: true });
      });
    });

    renderAssistantChat(<AssistantChat model="test-model" workspace="default" />);

    await userEvent.type(
      screen.getByRole('textbox', { name: /Task prompt/i }),
      'Hang before stream'
    );
    await userEvent.click(screen.getByRole('button', { name: /Submit/i }));

    await waitFor(() => expect(requestSignal).toBeDefined());
    expect(requestSignal?.aborted).toBe(false);

    await userEvent.click(screen.getByRole('button', { name: /Stop/i }));

    await waitFor(() => expect(requestSignal?.aborted).toBe(true));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Stop/i })).not.toBeInTheDocument()
    );
    expect(screen.queryByText('aborted')).not.toBeInTheDocument();
  });
});
