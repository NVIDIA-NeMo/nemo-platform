// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  CANCELLED_STATUS,
  COMPLETE_STATUS,
} from '@nemo/common/src/components/AssistantChat/constants';
import {
  createClaudeCodeSession,
  streamClaudeCodeMessage,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { getAssistantTextFromClaudeEvent } from '@studio/routes/agents/ClaudeCodeChatRoute/stream';
import { useCustomAssistantChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useCustomAssistantChatRuntime';
import { useCallback, useRef, useState } from 'react';

export const useClaudeCodeChatRuntime = (options?: { onError?: (error: Error) => void }) => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);

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
