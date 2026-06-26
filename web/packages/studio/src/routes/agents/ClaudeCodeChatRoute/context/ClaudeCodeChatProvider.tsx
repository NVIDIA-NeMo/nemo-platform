// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  readStoredActiveSessionId,
  writeStoredActiveSessionId,
} from '@studio/routes/agents/ClaudeCodeChatRoute/activeSessionStorage';
import { getClaudeCodeSessionHistory } from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import {
  ClaudeCodeChatContext,
  type ClaudeCodeChatLoadStatus,
} from '@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext';
import { useClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { getClaudeCodeHistoryMessages } from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { type FC, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

interface ClaudeCodeChatProviderProps {
  children: ReactNode;
  workspace: string;
}

/**
 * Owns the single Code Agent chat runtime for a workspace. Mounted above both
 * the full chat route and the top-bar pop-out so an in-flight run (and its
 * thinking / awaiting-input state) survives navigating between them.
 */
export const ClaudeCodeChatProvider: FC<ClaudeCodeChatProviderProps> = ({
  children,
  workspace,
}) => {
  const location = useLocation();
  const toast = useToast();
  const [loadStatus, setLoadStatus] = useState<ClaudeCodeChatLoadStatus>('idle');
  const requestedSessionIdRef = useRef<string | null>(null);

  const handleSessionIdChange = useCallback(
    (nextSessionId: string | null) => {
      writeStoredActiveSessionId(workspace, nextSessionId?.trim() || null);
    },
    [workspace]
  );

  const handleError = useCallback((error: Error) => toast.error(error.message), [toast]);

  const chat = useClaudeCodeChatRuntime({
    onError: handleError,
    onSessionIdChange: handleSessionIdChange,
    studioPathname: `${location.pathname}${location.search}`,
    workspace,
  });
  const { handleReset, loadSession: applySession, sessionId } = chat;

  const loadSession = useCallback(
    async (nextSessionId: string) => {
      const trimmedSessionId = nextSessionId.trim();
      if (!trimmedSessionId || trimmedSessionId === sessionId) return;

      requestedSessionIdRef.current = trimmedSessionId;
      setLoadStatus('loading');

      try {
        const history = await getClaudeCodeSessionHistory(trimmedSessionId);
        // Ignore a stale fetch if a newer session was requested meanwhile.
        if (requestedSessionIdRef.current !== trimmedSessionId) return;

        applySession({
          artifacts: history.chat_artifacts,
          messages: getClaudeCodeHistoryMessages(history),
          sessionId: history.session_id,
        });
        setLoadStatus('idle');
      } catch (error: unknown) {
        if (requestedSessionIdRef.current !== trimmedSessionId) return;
        setLoadStatus('error');
        toast.error(error instanceof Error ? error.message : 'Could not load Claude Code session.');
      }
    },
    [applySession, sessionId, toast]
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
    if (storedSessionId) void loadSession(storedSessionId);
  }, [loadSession, workspace]);

  const value = useMemo(
    () => ({ chat, loadStatus, loadSession, startNewChat }),
    [chat, loadSession, loadStatus, startNewChat]
  );

  return <ClaudeCodeChatContext.Provider value={value}>{children}</ClaudeCodeChatContext.Provider>;
};
