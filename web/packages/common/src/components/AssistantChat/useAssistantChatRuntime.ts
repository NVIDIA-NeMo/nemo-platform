// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type AppendMessage,
  type MessageStatus,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from '@assistant-ui/react';
import {
  getCompletionText,
  isAbortError,
  isChatCompletionStream,
} from '@nemo/common/src/components/AssistantChat/completionUtils';
import {
  CANCELLED_STATUS,
  COMPLETE_STATUS,
  RUNNING_STATUS,
} from '@nemo/common/src/components/AssistantChat/constants';
import {
  appendMessageToThreadMessage,
  createTextMessage,
  getEditedMessageIndex,
  getMessageText,
  getOpenAIMessages,
} from '@nemo/common/src/components/AssistantChat/messageUtils';
import {
  findStudioTool,
  isStudioTool,
  toOpenAITool,
} from '@nemo/common/src/components/AssistantChat/tools';
import type {
  AssistantChatTool,
  StudioTool,
} from '@nemo/common/src/components/AssistantChat/tools/types';
import type { AssistantChatProps } from '@nemo/common/src/components/AssistantChat/types';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import type { ChatCompletionTool } from 'openai/resources/index.mjs';
import { useCallback, useRef, useState } from 'react';

const MAX_TOOL_ROUNDS = 5;

type UseAssistantChatRuntimeOptions = Pick<
  AssistantChatProps,
  | 'baseURL'
  | 'disabled'
  | 'initialMessages'
  | 'model'
  | 'onError'
  | 'promptData'
  | 'tools'
  | 'workspace'
> & {
  readonly enabledStudioToolNames?: ReadonlySet<string>;
};

interface AccumulatingToolCall {
  id: string;
  name: string;
  argsText: string;
}

interface StreamRoundResult {
  text: string;
  toolCalls: Map<number, AccumulatingToolCall>;
  finished: 'complete' | 'cancelled';
}

const buildAssistantContent = (
  text: string,
  toolCalls: ReadonlyMap<number, AccumulatingToolCall>,
  resultsByCallId?: ReadonlyMap<string, { result: unknown; isError: boolean }>
): ThreadMessageLike['content'] => {
  const parts: Exclude<ThreadMessageLike['content'], string>[number][] = [];
  if (text) parts.push({ type: 'text', text });

  const orderedToolCalls = [...toolCalls.entries()].sort(([a], [b]) => a - b);
  for (const [index, toolCall] of orderedToolCalls) {
    if (!toolCall.name) continue;
    const toolCallId = toolCall.id || `tool-call-${index}`;
    const matched = resultsByCallId?.get(toolCallId);
    parts.push({
      type: 'tool-call',
      toolCallId,
      toolName: toolCall.name,
      argsText: toolCall.argsText,
      ...(matched ? { result: matched.result, isError: matched.isError } : {}),
    });
  }

  if (!parts.length) parts.push({ type: 'text', text: '' });
  return parts;
};

const parseToolArgs = (argsText: string): Record<string, unknown> => {
  if (!argsText) return {};
  try {
    const parsed = JSON.parse(argsText);
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
};

export const useAssistantChatRuntime = ({
  model,
  workspace,
  baseURL,
  promptData,
  tools,
  enabledStudioToolNames,
  disabled = false,
  initialMessages = [],
  onError,
}: UseAssistantChatRuntimeOptions) => {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>(initialMessages);
  const [isRunning, setIsRunning] = useState(false);
  const messagesRef = useRef<readonly ThreadMessageLike[]>(initialMessages);
  const abortControllerRef = useRef<AbortController | null>(null);
  const { mutateAsync: createChatCompletion } = useChatCompletion();

  const toolsRef = useRef<readonly AssistantChatTool[]>(tools ?? []);
  toolsRef.current = tools ?? [];
  const enabledNamesRef = useRef<ReadonlySet<string>>(enabledStudioToolNames ?? new Set());
  enabledNamesRef.current = enabledStudioToolNames ?? new Set();

  const setThreadMessages = useCallback((nextMessages: readonly ThreadMessageLike[]) => {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
  }, []);

  const updateAssistantMessage = useCallback(
    (assistantMessageId: string, content: ThreadMessageLike['content'], status: MessageStatus) => {
      setThreadMessages(
        messagesRef.current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content,
                status,
              }
            : message
        )
      );
    },
    [setThreadMessages]
  );

  const buildToolList = useCallback((): ChatCompletionTool[] | undefined => {
    const enabled = enabledNamesRef.current;
    const merged = toolsRef.current.flatMap((tool) => {
      if (isStudioTool(tool) && !enabled.has(tool.name)) return [];
      return [toOpenAITool(tool)];
    });
    return merged.length ? merged : undefined;
  }, []);

  const streamRound = useCallback(
    async (
      conversationMessages: readonly ThreadMessageLike[],
      assistantMessageId: string,
      runController: AbortController,
      isCurrentRun: () => boolean,
      allowTools: boolean
    ): Promise<StreamRoundResult> => {
      let responseText = '';
      const toolCalls = new Map<number, AccumulatingToolCall>();

      const result = await createChatCompletion({
        model,
        workspace,
        baseURL,
        messages: getOpenAIMessages(conversationMessages, promptData?.system_prompt),
        max_tokens: promptData?.inference_params?.max_tokens,
        temperature: promptData?.inference_params?.temperature,
        stream: true,
        tools: allowTools ? buildToolList() : undefined,
        signal: runController.signal,
      });

      if (runController.signal.aborted || !isCurrentRun()) {
        return { text: responseText, toolCalls, finished: 'cancelled' };
      }

      if (isChatCompletionStream(result)) {
        const streamController = result.controller;
        runController.signal.addEventListener('abort', () => streamController.abort(), {
          once: true,
        });
        if (runController.signal.aborted) streamController.abort();

        for await (const chunk of result) {
          if (runController.signal.aborted || !isCurrentRun()) break;
          const delta = chunk.choices[0]?.delta;
          responseText += delta?.content ?? '';
          for (const toolCallDelta of delta?.tool_calls ?? []) {
            const existing = toolCalls.get(toolCallDelta.index) ?? {
              id: '',
              name: '',
              argsText: '',
            };
            if (toolCallDelta.id) existing.id = toolCallDelta.id;
            if (toolCallDelta.function?.name) existing.name = toolCallDelta.function.name;
            if (toolCallDelta.function?.arguments)
              existing.argsText += toolCallDelta.function.arguments;
            toolCalls.set(toolCallDelta.index, existing);
          }
          updateAssistantMessage(
            assistantMessageId,
            buildAssistantContent(responseText, toolCalls),
            RUNNING_STATUS
          );
        }

        return {
          text: responseText,
          toolCalls,
          finished: runController.signal.aborted ? 'cancelled' : 'complete',
        };
      }

      responseText = getCompletionText(result);
      for (const [index, toolCall] of result.choices[0]?.message.tool_calls?.entries() ?? []) {
        toolCalls.set(index, {
          id: toolCall.id,
          name: toolCall.function.name,
          argsText: toolCall.function.arguments,
        });
      }
      return { text: responseText, toolCalls, finished: 'complete' };
    },
    [
      baseURL,
      buildToolList,
      createChatCompletion,
      model,
      promptData?.inference_params?.max_tokens,
      promptData?.inference_params?.temperature,
      promptData?.system_prompt,
      updateAssistantMessage,
      workspace,
    ]
  );

  const executeToolCalls = useCallback(
    async (
      toolCalls: ReadonlyMap<number, AccumulatingToolCall>,
      signal: AbortSignal
    ): Promise<Map<string, { result: unknown; isError: boolean }>> => {
      const callable = [...toolCalls.entries()]
        .map(([index, call]) => ({
          index,
          callId: call.id || `tool-call-${index}`,
          name: call.name,
          argsText: call.argsText,
          tool: findStudioTool(
            toolsRef.current.filter((tool): tool is StudioTool => isStudioTool(tool)),
            call.name
          ),
        }))
        .filter((entry) => entry.name);

      const outcomes = await Promise.all(
        callable.map(async (entry) => {
          if (!entry.tool) {
            return {
              callId: entry.callId,
              result: { error: `Tool "${entry.name}" is not registered in this Studio build.` },
              isError: true,
            };
          }
          try {
            const args = parseToolArgs(entry.argsText);
            const outcome = await entry.tool.execute(args, { signal });
            if (outcome.ok) {
              return { callId: entry.callId, result: outcome.result, isError: false };
            }
            return { callId: entry.callId, result: { error: outcome.error }, isError: true };
          } catch (error: unknown) {
            if (isAbortError(error)) {
              return {
                callId: entry.callId,
                result: { error: 'Tool execution cancelled.' },
                isError: true,
              };
            }
            const message = error instanceof Error ? error.message : 'Unknown tool error.';
            return { callId: entry.callId, result: { error: message }, isError: true };
          }
        })
      );

      return new Map(outcomes.map((o) => [o.callId, { result: o.result, isError: o.isError }]));
    },
    []
  );

  const runCompletion = useCallback(
    async (conversationMessages: readonly ThreadMessageLike[]) => {
      if (disabled) return;

      abortControllerRef.current?.abort();
      const runController = new AbortController();
      abortControllerRef.current = runController;
      const isCurrentRun = () => abortControllerRef.current === runController;

      let history = conversationMessages;
      let allowTools = true;
      setIsRunning(true);

      try {
        for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
          if (runController.signal.aborted || !isCurrentRun()) return;

          const assistantMessage = createTextMessage('assistant', '', RUNNING_STATUS);
          history = [...history, assistantMessage];
          setThreadMessages(history);

          const { text, toolCalls, finished } = await streamRound(
            history.slice(0, -1),
            assistantMessage.id!,
            runController,
            isCurrentRun,
            allowTools
          );

          if (finished === 'cancelled' || runController.signal.aborted) {
            updateAssistantMessage(
              assistantMessage.id!,
              buildAssistantContent(text, toolCalls),
              CANCELLED_STATUS
            );
            return;
          }

          const executableCalls = new Map([...toolCalls.entries()].filter(([, call]) => call.name));

          if (executableCalls.size === 0) {
            updateAssistantMessage(
              assistantMessage.id!,
              buildAssistantContent(text, toolCalls),
              COMPLETE_STATUS
            );
            return;
          }

          const results = await executeToolCalls(executableCalls, runController.signal);

          if (runController.signal.aborted || !isCurrentRun()) {
            updateAssistantMessage(
              assistantMessage.id!,
              buildAssistantContent(text, toolCalls, results),
              CANCELLED_STATUS
            );
            return;
          }

          const mergedContent = buildAssistantContent(text, toolCalls, results);
          updateAssistantMessage(assistantMessage.id!, mergedContent, COMPLETE_STATUS);

          history = messagesRef.current;
          allowTools = false;
        }

        // Hit the round cap — leave the latest assistant message as-is.
      } catch (error: unknown) {
        const lastMessageId =
          messagesRef.current[messagesRef.current.length - 1]?.role === 'assistant'
            ? messagesRef.current[messagesRef.current.length - 1]?.id
            : undefined;

        if (runController.signal.aborted || isAbortError(error)) {
          if (lastMessageId) {
            const last = messagesRef.current[messagesRef.current.length - 1];
            updateAssistantMessage(lastMessageId, last.content, CANCELLED_STATUS);
          }
          return;
        }

        const errorMessage = error instanceof Error ? error.message : 'Unknown Error';
        const status: MessageStatus = {
          type: 'incomplete',
          reason: 'error',
          error: errorMessage,
        };
        if (lastMessageId) {
          updateAssistantMessage(lastMessageId, [{ type: 'text', text: errorMessage }], status);
        }
        onError?.(error instanceof Error ? error : new Error(errorMessage));
      } finally {
        if (abortControllerRef.current === runController) {
          abortControllerRef.current = null;
          setIsRunning(false);
        }
      }
    },
    [disabled, executeToolCalls, onError, setThreadMessages, streamRound, updateAssistantMessage]
  );

  const handleNewMessage = useCallback(
    async (message: AppendMessage) => {
      const text = getMessageText(message).trim();
      if (!text) return;

      const userMessage = appendMessageToThreadMessage({
        ...message,
        content: [{ type: 'text', text }],
      });
      const nextMessages = [...messagesRef.current, userMessage];
      setThreadMessages(nextMessages);
      await runCompletion(nextMessages);
    },
    [runCompletion, setThreadMessages]
  );

  const handleReload = useCallback(async () => {
    const lastAssistantIndex = messagesRef.current.findLastIndex(
      (message) => message.role === 'assistant'
    );
    const nextMessages =
      lastAssistantIndex === -1
        ? messagesRef.current
        : messagesRef.current.slice(0, lastAssistantIndex);

    setThreadMessages(nextMessages);
    await runCompletion(nextMessages);
  }, [runCompletion, setThreadMessages]);

  const handleEdit = useCallback(
    async (message: AppendMessage) => {
      const sourceIndex = getEditedMessageIndex(messagesRef.current, message);
      const previousMessages =
        sourceIndex === -1 ? messagesRef.current : messagesRef.current.slice(0, sourceIndex);
      const text = getMessageText(message).trim();
      if (!text) return;

      const nextMessages = [
        ...previousMessages,
        appendMessageToThreadMessage({
          ...message,
          content: [{ type: 'text', text }],
        }),
      ];
      setThreadMessages(nextMessages);
      await runCompletion(nextMessages);
    },
    [runCompletion, setThreadMessages]
  );

  const handleCancel = useCallback(async () => {
    abortControllerRef.current?.abort();
    setIsRunning(false);
    setThreadMessages(
      messagesRef.current.map((message) =>
        message.role === 'assistant' && message.status?.type === 'running'
          ? { ...message, status: CANCELLED_STATUS }
          : message
      )
    );
  }, [setThreadMessages]);

  const handleReset = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsRunning(false);
    setThreadMessages([]);
  }, [setThreadMessages]);

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    setMessages: setThreadMessages,
    isDisabled: disabled,
    isRunning,
    onNew: handleNewMessage,
    onEdit: handleEdit,
    onReload: async () => handleReload(),
    onCancel: handleCancel,
    convertMessage: (message) => message,
    unstable_capabilities: {
      copy: true,
    },
  });

  return {
    handleReset,
    runtime,
  };
};
