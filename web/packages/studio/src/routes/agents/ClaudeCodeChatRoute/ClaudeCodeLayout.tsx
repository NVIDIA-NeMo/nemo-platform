// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { ClaudeCodeHistoryPanel } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeHistoryPanel';
import type { ClaudeCodeChatArtifacts } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getClaudeCodeChatRouteForSession } from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { type FC, type ReactNode, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

interface ClaudeCodeLayoutProps {
  activeSessionId?: string;
  artifacts?: ClaudeCodeChatArtifacts;
  children: ReactNode;
  hideArtifacts?: boolean;
  onNewChat?: () => void;
}

export const ClaudeCodeLayout: FC<ClaudeCodeLayoutProps> = ({
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
      navigate(getClaudeCodeChatRouteForSession(workspace, sessionId));
    },
    [navigate, workspace]
  );

  return (
    <Flex className="h-full min-h-[calc(100vh-var(--nv-app-bar-height))] w-full flex-col bg-surface-sunken text-primary dark:bg-surface-raised lg:flex-row">
      <Flex className="h-full min-h-0 min-w-0 flex-1">{children}</Flex>
      <ClaudeCodeHistoryPanel
        activeSessionId={activeSessionId}
        artifacts={artifacts}
        hideArtifacts={hideArtifacts}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
      />
    </Flex>
  );
};
