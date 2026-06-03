// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { ClaudeCodeHistoryPanel } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeHistoryPanel';
import { getClaudeCodeChatRouteForSession } from '@studio/routes/agents/ClaudeCodeChatRoute/history';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';
import { type FC, type ReactNode, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

interface ClaudeCodeLayoutProps {
  activeSessionId?: string;
  children: ReactNode;
}

export const ClaudeCodeLayout: FC<ClaudeCodeLayoutProps> = ({ activeSessionId, children }) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  const handleNewChat = useCallback(() => {
    navigate(getClaudeCodeChatRoute(workspace));
  }, [navigate, workspace]);

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      navigate(getClaudeCodeChatRouteForSession(workspace, sessionId));
    },
    [navigate, workspace]
  );

  return (
    <div className="flex h-full min-h-[calc(100vh-var(--nv-app-bar-height))] flex-col bg-surface-sunken text-primary lg:flex-row">
      <div className="min-h-0 min-w-0 flex-1">{children}</div>
      <ClaudeCodeHistoryPanel
        activeSessionId={activeSessionId}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
      />
    </div>
  );
};
