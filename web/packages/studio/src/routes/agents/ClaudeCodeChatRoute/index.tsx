// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ClaudeCodeChatThread } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeChatThread';
import { ClaudeCodeLayout } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeLayout';
import { useClaudeCodeChatContext } from '@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import {
  CLAUDE_CODE_SESSION_SEARCH_PARAM,
  getSelectedClaudeCodeSessionId,
} from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { getClaudeCodeChatRoute, getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { type FC, useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const getInitialPrompt = (state: unknown): string | undefined => {
  if (typeof state !== 'object' || state === null) return undefined;

  const initialPrompt = (state as ClaudeCodeChatRouteState).initialPrompt;
  if (typeof initialPrompt !== 'string') return undefined;

  const trimmedPrompt = initialPrompt.trim();
  return trimmedPrompt || undefined;
};

const ClaudeCodeChatLoadingState = ({ selectedSessionId }: { selectedSessionId?: string }) => (
  <ClaudeCodeLayout activeSessionId={selectedSessionId}>
    <Stack className="h-full w-full" padding="density-2xl">
      <Stack className="mx-auto min-h-0 w-full max-w-180 flex-1" align="center" justify="center">
        <Text kind="body/regular/md" color="secondary">
          Loading chat...
        </Text>
      </Stack>
    </Stack>
  </ClaudeCodeLayout>
);

const ClaudeCodeChatErrorState = ({ selectedSessionId }: { selectedSessionId?: string }) => (
  <ClaudeCodeLayout activeSessionId={selectedSessionId}>
    <Stack className="h-full w-full" padding="density-2xl">
      <Stack className="mx-auto min-h-0 w-full max-w-180 flex-1" align="center" justify="center">
        <Banner kind="inline" status="error">
          Could not load Claude Code session.
        </Banner>
      </Stack>
    </Stack>
  </ClaudeCodeLayout>
);

export const ClaudeCodeChatRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const navigate = useNavigate();
  const { chat, loadStatus, loadSession, startNewChat } = useClaudeCodeChatContext();
  const { artifacts, sessionId, submitPrompt } = chat;
  const selectedSessionId = getSelectedClaudeCodeSessionId(location.search);
  const initialPrompt = getInitialPrompt(location.state);

  const [displayedSessionId, setDisplayedSessionId] = useState<string | null>(sessionId);
  useEffect(() => {
    setDisplayedSessionId(sessionId);
  }, [sessionId]);

  useBreadcrumbs({
    items: [
      { slotLabel: 'Dashboard', href: getWorkspaceDashboardRoute(workspace) },
      { slotLabel: 'Code Agent' },
    ],
  });

  // Point the shared runtime at the session selected via the URL.
  // Skip when initialPrompt is set — that effect will clear the ?session= param
  // and start a fresh chat; letting both effects run in parallel causes loadSession
  // to race against startNewChat on the same render.
  useEffect(() => {
    if (initialPrompt) return;
    if (selectedSessionId && selectedSessionId !== sessionId) {
      loadSession(selectedSessionId);
    }
  }, [initialPrompt, loadSession, selectedSessionId, sessionId]);

  // Consume a dashboard-provided prompt exactly once: start fresh and defer
  // submission until the session is actually cleared.
  // submitPrompt cannot be called in the same synchronous block as startNewChat
  // because setSessionId(null) is a scheduled React update — ensureSessionId
  // would still close over the old ID and send the prompt to the wrong session.
  const [deferredPrompt, setDeferredPrompt] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!initialPrompt) return;
    const params = new URLSearchParams(location.search);
    params.delete(CLAUDE_CODE_SESSION_SEARCH_PARAM);
    const search = params.toString();
    navigate(`${location.pathname}${search ? `?${search}` : ''}`, { replace: true, state: null });
    startNewChat();
    setDeferredPrompt(initialPrompt);
  }, [initialPrompt, location.pathname, location.search, navigate, startNewChat]);

  // Submit once sessionId is null (reset complete). Also handles the case where
  // sessionId was already null when the prompt arrived.
  useEffect(() => {
    if (!deferredPrompt || sessionId !== null) return;
    setDeferredPrompt(undefined);
    void submitPrompt(deferredPrompt);
  }, [deferredPrompt, sessionId, submitPrompt]);

  const handleChatReset = useCallback(() => {
    if (selectedSessionId) {
      navigate(getClaudeCodeChatRoute(workspace), { replace: true });
    }
  }, [navigate, selectedSessionId, workspace]);

  const isLoadingSelectedSession =
    selectedSessionId !== undefined && selectedSessionId !== displayedSessionId;

  if (isLoadingSelectedSession && loadStatus !== 'error') {
    return <ClaudeCodeChatLoadingState selectedSessionId={selectedSessionId} />;
  }

  if (isLoadingSelectedSession && loadStatus === 'error') {
    return <ClaudeCodeChatErrorState selectedSessionId={selectedSessionId} />;
  }

  return (
    <ClaudeCodeLayout
      activeSessionId={sessionId ?? undefined}
      artifacts={artifacts}
      onNewChat={startNewChat}
    >
      <AccessibleTitle title={`Code Agent chat for ${workspace}`}>
        <Stack className="h-full w-full py-density-lg">
          <Stack className="min-h-0 w-full flex-1">
            <ClaudeCodeChatThread chat={chat} onReset={handleChatReset} />
          </Stack>
        </Stack>
      </AccessibleTitle>
    </ClaudeCodeLayout>
  );
};
