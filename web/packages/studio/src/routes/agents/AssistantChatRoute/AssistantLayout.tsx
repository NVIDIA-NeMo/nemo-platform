// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { AssistantHistoryPanel } from '@studio/routes/agents/AssistantChatRoute/AssistantHistoryPanel';
import type { AssistantChatArtifacts } from '@studio/routes/agents/AssistantChatRoute/types';
import { getAssistantChatRouteForSession } from '@studio/routes/agents/AssistantChatRoute/util';
import { getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { type FC, type ReactNode, useCallback } from 'react';
import { useNavigate } from 'react-router';

interface AssistantLayoutProps {
  activeSessionId?: string;
  artifacts?: AssistantChatArtifacts;
  children: ReactNode;
  hideArtifacts?: boolean;
  onNewChat?: () => void;
}

export const AssistantLayout: FC<AssistantLayoutProps> = ({
  activeSessionId,
  artifacts,
  children,
  hideArtifacts,
  onNewChat,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  const handleNewChat = useCallback(() => {
    onNewChat?.();
    navigate(getWorkspaceDashboardRoute(workspace));
  }, [navigate, onNewChat, workspace]);

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      // Navigating to the session URL drives the shared runtime to load it
      // (which also persists it as the active session via onSessionIdChange).
      navigate(getAssistantChatRouteForSession(workspace, sessionId));
    },
    [navigate, workspace]
  );

  return (
    <Flex className="h-full min-h-[calc(100vh-var(--nv-app-bar-height))] w-full flex-col bg-surface-sunken text-primary dark:bg-surface-base lg:flex-row">
      <Flex className="h-full min-h-0 min-w-0 flex-1">{children}</Flex>
      <AssistantHistoryPanel
        activeSessionId={activeSessionId}
        artifacts={artifacts}
        hideArtifacts={hideArtifacts}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        workspace={workspace}
      />
    </Flex>
  );
};
