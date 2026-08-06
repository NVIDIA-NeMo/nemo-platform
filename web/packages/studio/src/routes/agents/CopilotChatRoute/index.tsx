// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { useCopilotChatContext } from '@studio/routes/agents/CopilotChatRoute/context/useCopilotChatContext';
import { CopilotChatThread } from '@studio/routes/agents/CopilotChatRoute/CopilotChatThread';
import { CopilotLayout } from '@studio/routes/agents/CopilotChatRoute/CopilotLayout';
import type { CopilotChatRouteState } from '@studio/routes/agents/CopilotChatRoute/types';
import {
  COPILOT_SESSION_SEARCH_PARAM,
  getSelectedCopilotSessionId,
} from '@studio/routes/agents/CopilotChatRoute/util';
import { getCopilotChatRoute, getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { type FC, useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

const getInitialPrompt = (state: unknown): string | undefined => {
  if (typeof state !== 'object' || state === null) return undefined;

  const initialPrompt = (state as CopilotChatRouteState).initialPrompt;
  if (typeof initialPrompt !== 'string') return undefined;

  const trimmedPrompt = initialPrompt.trim();
  return trimmedPrompt || undefined;
};

const CopilotChatLoadingState = ({ selectedSessionId }: { selectedSessionId?: string }) => (
  <CopilotLayout activeSessionId={selectedSessionId}>
    <Stack className="h-full w-full" padding="density-2xl">
      <Stack className="mx-auto min-h-0 w-full max-w-180 flex-1" align="center" justify="center">
        <Text kind="body/regular/md" color="secondary">
          Loading chat...
        </Text>
      </Stack>
    </Stack>
  </CopilotLayout>
);

const CopilotChatErrorState = ({ selectedSessionId }: { selectedSessionId?: string }) => (
  <CopilotLayout activeSessionId={selectedSessionId}>
    <Stack className="h-full w-full" padding="density-2xl">
      <Stack className="mx-auto min-h-0 w-full max-w-180 flex-1" align="center" justify="center">
        <Banner kind="inline" status="error">
          Could not load NeMo Copilot session.
        </Banner>
      </Stack>
    </Stack>
  </CopilotLayout>
);

export const CopilotChatRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const navigate = useNavigate();
  const { chat, loadStatus, loadSession, startNewChat } = useCopilotChatContext();
  const { artifacts, sessionId, submitPrompt } = chat;
  const selectedSessionId = getSelectedCopilotSessionId(location.search);
  const initialPrompt = getInitialPrompt(location.state);

  const [displayedSessionId, setDisplayedSessionId] = useState<string | null>(sessionId);
  useEffect(() => {
    setDisplayedSessionId(sessionId);
  }, [sessionId]);

  useBreadcrumbs({
    items: [
      { slotLabel: 'Dashboard', href: getWorkspaceDashboardRoute(workspace) },
      { slotLabel: 'NeMo Copilot' },
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
    params.delete(COPILOT_SESSION_SEARCH_PARAM);
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
      navigate(getCopilotChatRoute(workspace), { replace: true });
    }
  }, [navigate, selectedSessionId, workspace]);

  const isLoadingSelectedSession =
    selectedSessionId !== undefined && selectedSessionId !== displayedSessionId;

  if (isLoadingSelectedSession && loadStatus !== 'error') {
    return <CopilotChatLoadingState selectedSessionId={selectedSessionId} />;
  }

  if (isLoadingSelectedSession && loadStatus === 'error') {
    return <CopilotChatErrorState selectedSessionId={selectedSessionId} />;
  }

  return (
    <CopilotLayout
      activeSessionId={sessionId ?? undefined}
      artifacts={artifacts}
      onNewChat={startNewChat}
    >
      <AccessibleTitle title={`NeMo Copilot chat for ${workspace}`}>
        <Stack className="h-full w-full py-density-lg">
          <Stack className="min-h-0 w-full flex-1">
            <CopilotChatThread chat={chat} onReset={handleChatReset} />
          </Stack>
        </Stack>
      </AccessibleTitle>
    </CopilotLayout>
  );
};
