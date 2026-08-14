// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  readStoredActiveSessionId,
  writeStoredActiveSessionId,
} from '@studio/routes/agents/AssistantChatRoute/activeSessionStorage';
import {
  AssistantSessionNotFoundError,
  getAssistantSessionHistory,
} from '@studio/routes/agents/AssistantChatRoute/api';
import {
  AssistantChatContext,
  type AssistantChatLoadStatus,
} from '@studio/routes/agents/AssistantChatRoute/context/useAssistantChatContext';
import { useAssistantChatRuntime } from '@studio/routes/agents/AssistantChatRoute/useAssistantChatRuntime';
import { getAssistantHistoryMessages } from '@studio/routes/agents/AssistantChatRoute/util';
import { type FC, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router';

interface AssistantChatProviderProps {
  children: ReactNode;
  workspace: string;
}

/**
 * Owns the single NeMo Assistant chat runtime for a workspace. Mounted above both
 * the full chat route and the top-bar pop-out so an in-flight run (and its
 * thinking / awaiting-input state) survives navigating between them.
 */
export const AssistantChatProvider: FC<AssistantChatProviderProps> = ({ children, workspace }) => {
  const location = useLocation();
  const toast = useToast();
  const [loadStatus, setLoadStatus] = useState<AssistantChatLoadStatus>('idle');
  const requestedSessionIdRef = useRef<string | null>(null);

  const handleSessionIdChange = useCallback(
    (nextSessionId: string | null) => {
      writeStoredActiveSessionId(workspace, nextSessionId?.trim() || null);
    },
    [workspace]
  );

  const handleError = useCallback((error: Error) => toast.error(error.message), [toast]);

  const chat = useAssistantChatRuntime({
    onError: handleError,
    onSessionIdChange: handleSessionIdChange,
    studioPathname: `${location.pathname}${location.search}`,
    workspace,
  });
  const { handleReset, loadSession: applySession, sessionId } = chat;

  const loadSession = useCallback(
    async (nextSessionId: string, forgetIfMissing = false) => {
      const trimmedSessionId = nextSessionId.trim();
      if (!trimmedSessionId || trimmedSessionId === sessionId) return;

      requestedSessionIdRef.current = trimmedSessionId;
      setLoadStatus('loading');

      try {
        const history = await getAssistantSessionHistory(trimmedSessionId, workspace);
        // Ignore a stale fetch if a newer session was requested meanwhile.
        if (requestedSessionIdRef.current !== trimmedSessionId) return;

        applySession({
          artifacts: history.chat_artifacts,
          messages: getAssistantHistoryMessages(history),
          sessionId: history.session_id,
        });
        setLoadStatus('idle');
      } catch (error: unknown) {
        if (requestedSessionIdRef.current !== trimmedSessionId) return;
        if (forgetIfMissing && error instanceof AssistantSessionNotFoundError) {
          requestedSessionIdRef.current = null;
          writeStoredActiveSessionId(workspace, null);
          setLoadStatus('idle');
          return;
        }
        setLoadStatus('error');
        toast.error(
          error instanceof Error ? error.message : 'Could not load NeMo Assistant session.'
        );
      }
    },
    [applySession, sessionId, toast, workspace]
  );

  // Starting a new chat must cancel any in-flight session load, otherwise a
  // late history response would rehydrate the previous session over the reset.
  const startNewChat = useCallback(() => {
    requestedSessionIdRef.current = null;
    handleReset();
  }, [handleReset]);

  // Cold start: restore the last active session once on mount so the pop-out
  // (and full chat) reflect it after a hard refresh on any workspace page.
  const hasHydratedRef = useRef(false);
  useEffect(() => {
    if (hasHydratedRef.current) return;
    hasHydratedRef.current = true;

    const storedSessionId = readStoredActiveSessionId(workspace);
    if (storedSessionId) void loadSession(storedSessionId, true);
  }, [loadSession, workspace]);

  const value = useMemo(
    () => ({ chat, loadStatus, loadSession, startNewChat }),
    [chat, loadSession, loadStatus, startNewChat]
  );

  return <AssistantChatContext.Provider value={value}>{children}</AssistantChatContext.Provider>;
};
