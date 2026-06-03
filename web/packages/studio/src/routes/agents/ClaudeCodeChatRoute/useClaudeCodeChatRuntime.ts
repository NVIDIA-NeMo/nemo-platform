// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import {
  CANCELLED_STATUS,
  COMPLETE_STATUS,
} from '@nemo/common/src/components/AssistantChat/constants';
import {
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
  createClaudeCodeSession,
  streamClaudeCodeMessage,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { getAssistantTextFromClaudeEvent } from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import { useCustomAssistantChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';

interface UseClaudeCodeChatRuntimeOptions {
  initialMessages?: readonly ThreadMessageLike[];
  initialSessionId?: string;
  onError?: (error: Error) => void;
}

export const useClaudeCodeChatRuntime = (options?: UseClaudeCodeChatRuntimeOptions) => {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(options?.initialSessionId ?? null);
  const sessionIdRef = useRef<string | null>(options?.initialSessionId ?? null);

  const ensureSessionId = useCallback(async (): Promise<string> => {
    if (sessionIdRef.current) return sessionIdRef.current;

    const nextSessionId = await createClaudeCodeSession();
    sessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);
    return nextSessionId;
  }, []);

  const {
    handleReset: resetThread,
    isRunning,
    runtime,
    submitPrompt,
  } = useCustomAssistantChatRuntime({
    initialMessages: options?.initialMessages,
    onError: options?.onError,
    onRun: async ({ prompt, signal, appendAssistantText, isCurrentRun }) => {
      const activeSessionId = await ensureSessionId();
      let doneReceived = false;

      await streamClaudeCodeMessage({
        sessionId: activeSessionId,
        message: prompt,
        signal,
        handlers: {
          onClaudeEvent: (event) => {
            if (signal.aborted || !isCurrentRun()) return;

            const text = getAssistantTextFromClaudeEvent(event);
            if (text) appendAssistantText(text);
          },
          onDone: () => {
            doneReceived = true;
          },
          onError: (error) => {
            throw error;
          },
        },
      });
      void queryClient.invalidateQueries({ queryKey: CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY });

      return { status: doneReceived ? COMPLETE_STATUS : CANCELLED_STATUS };
    },
  });

  const handleReset = useCallback(() => {
    sessionIdRef.current = null;
    setSessionId(null);
    resetThread();
  }, [resetThread]);

  return {
    handleReset,
    isRunning,
    runtime,
    sessionId,
    submitPrompt,
  };
};
