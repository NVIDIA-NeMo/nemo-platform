// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type AppendMessage,
  type MessageStatus,
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
  prepareForUserInput: () => void;
  setAssistantText: (text: string) => void;
  isCurrentRun: () => boolean;
}

export interface CustomAssistantRunResult {
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

  const updateAssistantMessage = useCallback(
    (assistantMessageId: string, text: string, status: MessageStatus) => {
      setThreadMessages(
        messagesRef.current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: [{ type: 'text', text }],
                status,
              }
            : message
        )
      );
    },
    [setThreadMessages]
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

      let assistantMessageId: string | null = null;
      let responseText = '';

      const createAssistantMessage = () => {
        const assistantMessage = createTextMessage('assistant', '', RUNNING_STATUS);
        assistantMessageId = assistantMessage.id!;
        responseText = '';
        setThreadMessages([...messagesRef.current, assistantMessage]);
      };

      const ensureAssistantMessage = () => {
        if (assistantMessageId) return;
        createAssistantMessage();
      };

      createAssistantMessage();
      setIsRunning(true);

      const setAssistantText = (text: string) => {
        ensureAssistantMessage();
        responseText = text;
        updateAssistantMessage(assistantMessageId!, responseText, RUNNING_STATUS);
      };

      const appendAssistantText = (text: string) => {
        ensureAssistantMessage();
        responseText += text;
        updateAssistantMessage(assistantMessageId!, responseText, RUNNING_STATUS);
      };

      const prepareForUserInput = () => {
        if (!assistantMessageId) return;

        const currentAssistantMessageId = assistantMessageId;
        assistantMessageId = null;

        if (!responseText) {
          setThreadMessages(
            messagesRef.current.filter((message) => message.id !== currentAssistantMessageId)
          );
          return;
        }

        updateAssistantMessage(currentAssistantMessageId, responseText, COMPLETE_STATUS);
        responseText = '';
      };

      try {
        const result = await onRun({
          prompt,
          signal: runController.signal,
          appendAssistantText,
          prepareForUserInput,
          setAssistantText,
          isCurrentRun,
        });

        if (runController.signal.aborted || !isCurrentRun()) {
          if (assistantMessageId) {
            updateAssistantMessage(assistantMessageId, responseText, CANCELLED_STATUS);
          }
          return;
        }

        if (assistantMessageId) {
          updateAssistantMessage(
            assistantMessageId,
            result?.text ?? responseText,
            result?.status ?? COMPLETE_STATUS
          );
        }
      } catch (error: unknown) {
        if (runController.signal.aborted || isAbortError(error)) {
          if (assistantMessageId) {
            updateAssistantMessage(assistantMessageId, responseText, CANCELLED_STATUS);
          }
          return;
        }

        const errorMessage = error instanceof Error ? error.message : 'Unknown Error';
        ensureAssistantMessage();
        updateAssistantMessage(assistantMessageId!, errorMessage, {
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
    [onError, onRun, setThreadMessages, updateAssistantMessage]
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

  const appendUserMessage = useCallback(
    (message: string) => {
      const text = message.trim();
      if (!text) return;

      const userMessage = createTextMessage('user', text);
      setThreadMessages([...messagesRef.current, userMessage]);
    },
    [setThreadMessages]
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
    appendUserMessage,
    handleReset,
    isRunning,
    runtime,
    submitPrompt,
  };
};
