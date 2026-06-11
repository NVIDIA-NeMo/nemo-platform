// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantRuntimeProvider } from '@assistant-ui/react';
import { AssistantChatThread } from '@nemo/common/src/components/AssistantChat/AssistantChatThread';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Banner, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AgentDecisionInput } from '@studio/components/agents/AgentDecisionInput';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  getClaudeCodeSessionHistory,
  getClaudeCodeSessionHistoryQueryKey,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { ClaudeCodeLayout } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeLayout';
import { ClaudeCodeStudioLink } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { ClaudeCodeToolCallPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeToolCallPart';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { useClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import {
  getClaudeCodeHistoryMessages,
  getSelectedClaudeCodeSessionId,
} from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { getClaudeCodeChatRoute, getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { type FC, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const getInitialPrompt = (state: unknown): string | undefined => {
  if (typeof state !== 'object' || state === null) return undefined;

  const initialPrompt = (state as ClaudeCodeChatRouteState).initialPrompt;
  if (typeof initialPrompt !== 'string') return undefined;

  const trimmedPrompt = initialPrompt.trim();
  return trimmedPrompt || undefined;
};

interface ClaudeCodeChatSurfaceProps {
  initialMessages?: ReturnType<typeof getClaudeCodeHistoryMessages>;
  initialPrompt?: string;
  initialSessionId?: string;
}

const CHAT_VIEWPORT_SCROLLBAR_CLASS = [
  '[scrollbar-width:thin]',
  '[scrollbar-color:var(--border-color-interaction-base)_transparent]',
  '[&::-webkit-scrollbar]:w-2',
  '[&::-webkit-scrollbar-corner]:bg-transparent',
  '[&::-webkit-scrollbar-track]:bg-transparent',
  '[&::-webkit-scrollbar-thumb]:rounded-full',
  '[&::-webkit-scrollbar-thumb]:bg-[var(--border-color-interaction-base)]',
  '[&::-webkit-scrollbar-thumb:hover]:bg-[var(--border-color-interaction-strong)]',
].join(' ');

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

const ClaudeCodeChatSurface: FC<ClaudeCodeChatSurfaceProps> = ({
  initialMessages = [],
  initialPrompt,
  initialSessionId,
}) => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const consumedInitialPromptRef = useRef<string | undefined>(undefined);
  const chatViewportRef = useRef<HTMLDivElement>(null);
  const {
    decisionChoices,
    decisionRequest,
    decisionStatus,
    handleReset,
    resolveDecisionRequest,
    runtime,
    sessionId,
    skipDecisionRequest,
    submitPrompt,
  } = useClaudeCodeChatRuntime({
    initialMessages,
    initialSessionId,
    onError: (error) => toast.error(error.message),
    workspace,
  });
  const activeSessionId = initialSessionId ?? sessionId ?? undefined;

  const handleChatReset = useCallback(() => {
    handleReset();
    if (initialSessionId) {
      navigate(getClaudeCodeChatRoute(workspace), { replace: true });
    }
  }, [handleReset, initialSessionId, navigate, workspace]);

  useBreadcrumbs({
    items: [
      { slotLabel: 'Dashboard', href: getWorkspaceDashboardRoute(workspace) },
      { slotLabel: 'Code Agent' },
    ],
  });

  useEffect(() => {
    if (!initialPrompt || consumedInitialPromptRef.current === initialPrompt) return;

    consumedInitialPromptRef.current = initialPrompt;
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
    void submitPrompt(initialPrompt);
  }, [initialPrompt, location.pathname, location.search, navigate, submitPrompt]);

  useLayoutEffect(() => {
    if (!decisionRequest) return undefined;

    const viewport = chatViewportRef.current;
    if (!viewport) return undefined;

    const frame = window.requestAnimationFrame(() => {
      viewport.scrollTop = viewport.scrollHeight;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [decisionRequest]);

  return (
    <ClaudeCodeLayout activeSessionId={activeSessionId}>
      <AccessibleTitle title={`Code Agent chat for ${workspace}`}>
        <Stack className="h-full w-full py-density-lg">
          <Stack className="min-h-0 w-full flex-1">
            <AssistantRuntimeProvider runtime={runtime}>
              <AssistantChatThread
                contentClassName="mx-auto w-full max-w-180 px-density-2xl"
                composerContainerClassName="mx-auto w-full max-w-180 px-density-2xl"
                viewportClassName={CHAT_VIEWPORT_SCROLLBAR_CLASS}
                hideAssistantMessageActions
                toolCallPartComponent={ClaudeCodeToolCallPart}
                attributes={{
                  ThreadViewport: {
                    ref: chatViewportRef,
                  },
                }}
                placeholder="Ask Claude Code to work in this workspace"
                onReset={handleChatReset}
                showRunningIndicator={!decisionRequest}
                messageContentProps={{ markdownLinkComponent: ClaudeCodeStudioLink }}
                emptyState={{
                  slotHeading: 'Start a Claude Code session',
                  slotSubheading: 'Ask Claude Code to work in this workspace.',
                }}
                composerOverride={
                  decisionRequest ? (
                    <AgentDecisionInput
                      request={decisionRequest}
                      choices={decisionChoices}
                      defaultChoiceId={decisionChoices[0]?.id}
                      status={decisionStatus}
                      onSubmit={resolveDecisionRequest}
                      onSkip={skipDecisionRequest}
                    />
                  ) : undefined
                }
              />
            </AssistantRuntimeProvider>
          </Stack>
        </Stack>
      </AccessibleTitle>
    </ClaudeCodeLayout>
  );
};

export const ClaudeCodeChatRoute: FC = () => {
  const location = useLocation();
  const selectedSessionId = getSelectedClaudeCodeSessionId(location.search);
  const initialPrompt = getInitialPrompt(location.state);
  const sessionHistoryQuery = useQuery({
    queryKey: getClaudeCodeSessionHistoryQueryKey(selectedSessionId ?? ''),
    queryFn: () => getClaudeCodeSessionHistory(selectedSessionId ?? ''),
    enabled: !!selectedSessionId,
  });
  const initialMessages = useMemo(
    () => getClaudeCodeHistoryMessages(sessionHistoryQuery.data),
    [sessionHistoryQuery.data]
  );

  if (selectedSessionId && sessionHistoryQuery.isLoading) {
    return <ClaudeCodeChatLoadingState selectedSessionId={selectedSessionId} />;
  }

  if (selectedSessionId && sessionHistoryQuery.isError) {
    return <ClaudeCodeChatErrorState selectedSessionId={selectedSessionId} />;
  }

  return (
    <ClaudeCodeChatSurface
      key={selectedSessionId ?? 'new'}
      initialMessages={initialMessages}
      initialPrompt={selectedSessionId ? undefined : initialPrompt}
      initialSessionId={selectedSessionId}
    />
  );
};
