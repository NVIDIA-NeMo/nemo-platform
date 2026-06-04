// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type AppendMessage,
  type MessageStatus,
  type ThreadAssistantMessagePart,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from '@assistant-ui/react';
import {
  CANCELLED_STATUS,
  COMPLETE_STATUS,
  RUNNING_STATUS,
} from '@nemo/common/src/components/AssistantChat/constants';
import {
  appendMessageToThreadMessage,
  createTextMessage,
  getMessageText,
} from '@nemo/common/src/components/AssistantChat/messageUtils';
import { useCallback, useRef, useState } from 'react';

export interface CustomAssistantRunContext {
  prompt: string;
  signal: AbortSignal;
  appendAssistantText: (text: string) => void;
  appendAssistantParts: (parts: readonly ThreadAssistantMessagePart[]) => void;
  setAssistantText: (text: string) => void;
  isCurrentRun: () => boolean;
}

export interface CustomAssistantRunResult {
  content?: readonly ThreadAssistantMessagePart[];
  status?: MessageStatus;
  text?: string;
}

interface UseCustomAssistantChatRuntimeOptions {
  initialMessages?: readonly ThreadMessageLike[];
  onRun: (context: CustomAssistantRunContext) => Promise<CustomAssistantRunResult | void>;
  onError?: (error: Error) => void;
}

const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError';

const mergeAssistantParts = (
  currentParts: readonly ThreadAssistantMessagePart[],
  nextParts: readonly ThreadAssistantMessagePart[]
): readonly ThreadAssistantMessagePart[] => {
  const merged = [...currentParts];

  for (const part of nextParts) {
    if (part.type !== 'reasoning' && part.type !== 'text') {
      merged.push(part);
      continue;
    }

    const previousPart = merged.at(-1);
    if (previousPart?.type === part.type) {
      merged[merged.length - 1] = {
        ...previousPart,
        text: previousPart.text + part.text,
      };
      continue;
    }

    merged.push(part);
  }

  return merged;
};

const getAssistantPartsText = (parts: readonly ThreadAssistantMessagePart[]): string =>
  parts
    .map((part) => {
      if (part.type === 'reasoning' || part.type === 'text') return part.text;
      return '';
    })
    .join('');

const hasVisibleAssistantContent = (content: ThreadMessageLike['content']): boolean => {
  if (typeof content === 'string') return content.trim().length > 0;

  return content.some((part) => {
    if (part.type === 'reasoning' || part.type === 'text') return part.text.trim().length > 0;
    return true;
  });
};

export const useCustomAssistantChatRuntime = ({
  initialMessages = [],
  onRun,
  onError,
}: UseCustomAssistantChatRuntimeOptions) => {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>(initialMessages);
  const [isRunning, setIsRunning] = useState(false);
  const messagesRef = useRef<readonly ThreadMessageLike[]>(initialMessages);
  const abortControllerRef = useRef<AbortController | null>(null);

  const setThreadMessages = useCallback((nextMessages: readonly ThreadMessageLike[]) => {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
  }, []);

  const updateAssistantMessageContent = useCallback(
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

  const updateAssistantMessageText = useCallback(
    (assistantMessageId: string, text: string, status: MessageStatus) => {
      updateAssistantMessageContent(assistantMessageId, [{ type: 'text', text }], status);
    },
    [updateAssistantMessageContent]
  );

  const completeAssistantMessageContent = useCallback(
    (assistantMessageId: string, content: ThreadMessageLike['content'], status: MessageStatus) => {
      if (!hasVisibleAssistantContent(content)) {
        setThreadMessages(
          messagesRef.current.filter((message) => message.id !== assistantMessageId)
        );
        return;
      }

      updateAssistantMessageContent(assistantMessageId, content, status);
    },
    [setThreadMessages, updateAssistantMessageContent]
  );

  const runCompletion = useCallback(
    async (conversationMessages: readonly ThreadMessageLike[]) => {
      const latestMessage = conversationMessages.at(-1);
      const prompt = latestMessage ? getMessageText(latestMessage).trim() : '';
      if (!prompt) return;

      abortControllerRef.current?.abort();
      const runController = new AbortController();
      abortControllerRef.current = runController;
      const isCurrentRun = () => abortControllerRef.current === runController;

      const assistantMessage = createTextMessage('assistant', '', RUNNING_STATUS);
      setThreadMessages([...conversationMessages, assistantMessage]);
      setIsRunning(true);
      let responseText = '';
      let responseContent: readonly ThreadAssistantMessagePart[] | undefined;

      const setAssistantText = (text: string) => {
        responseText = text;
        responseContent = undefined;
        updateAssistantMessageText(assistantMessage.id!, responseText, RUNNING_STATUS);
      };

      const appendAssistantText = (text: string) => {
        responseText += text;
        responseContent = undefined;
        updateAssistantMessageText(assistantMessage.id!, responseText, RUNNING_STATUS);
      };

      const appendAssistantParts = (parts: readonly ThreadAssistantMessagePart[]) => {
        if (!parts.length) return;

        responseContent = mergeAssistantParts(responseContent ?? [], parts);
        responseText = getAssistantPartsText(responseContent);
        updateAssistantMessageContent(assistantMessage.id!, responseContent, RUNNING_STATUS);
      };

      try {
        const result = await onRun({
          prompt,
          signal: runController.signal,
          appendAssistantText,
          appendAssistantParts,
          setAssistantText,
          isCurrentRun,
        });

        if (runController.signal.aborted || !isCurrentRun()) {
          completeAssistantMessageContent(
            assistantMessage.id!,
            responseContent ?? [{ type: 'text', text: responseText }],
            CANCELLED_STATUS
          );
          return;
        }

        completeAssistantMessageContent(
          assistantMessage.id!,
          result?.content ??
            (result?.text !== undefined
              ? [{ type: 'text', text: result.text }]
              : (responseContent ?? [{ type: 'text', text: responseText }])),
          result?.status ?? COMPLETE_STATUS
        );
      } catch (error: unknown) {
        if (runController.signal.aborted || isAbortError(error)) {
          completeAssistantMessageContent(
            assistantMessage.id!,
            responseContent ?? [{ type: 'text', text: responseText }],
            CANCELLED_STATUS
          );
          return;
        }

        const errorMessage = error instanceof Error ? error.message : 'Unknown Error';
        updateAssistantMessageText(assistantMessage.id!, errorMessage, {
          type: 'incomplete',
          reason: 'error',
          error: errorMessage,
        });
        onError?.(error instanceof Error ? error : new Error(errorMessage));
      } finally {
        if (abortControllerRef.current === runController) {
          abortControllerRef.current = null;
          setIsRunning(false);
        }
      }
    },
    [
      completeAssistantMessageContent,
      onError,
      onRun,
      setThreadMessages,
      updateAssistantMessageContent,
      updateAssistantMessageText,
    ]
  );

  const handleNewMessage = useCallback(
    async (message: AppendMessage): Promise<void> => {
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

  const submitPrompt = useCallback(
    async (prompt: string): Promise<void> => {
      const text = prompt.trim();
      if (!text) return;

      const userMessage = createTextMessage('user', text);
      const nextMessages = [...messagesRef.current, userMessage];
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
    isRunning,
    onNew: handleNewMessage,
    onCancel: handleCancel,
    convertMessage: (message) => message,
    unstable_capabilities: {
      copy: true,
    },
  });

  return {
    handleReset,
    isRunning,
    runtime,
    submitPrompt,
  };
};
