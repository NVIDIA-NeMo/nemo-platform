// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Flex, Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import {
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
  listClaudeCodeHistorySessions,
} from '@studio/routes/agents/ClaudeCodeChatRoute/api';
import { HistoryPanelSkeleton } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/HistoryPanelSkeletons';
import { HistorySessionButton } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/HistorySessionButton';
import type { ClaudeCodeHistoryPanelProps } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/types';
import { useQuery } from '@tanstack/react-query';
import { MessageSquarePlus, RefreshCw } from 'lucide-react';

export const HistoryPanelContents = ({
  activeSessionId,
  onNewChat,
  onSelectSession,
}: ClaudeCodeHistoryPanelProps) => {
  const {
    data: sessions = [],
    error,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY,
    queryFn: listClaudeCodeHistorySessions,
    refetchOnMount: 'always',
  });

  return (
    <>
      <div className="border-b border-base px-density-md py-density-sm">
        <Flex align="center" gap="density-xs">
          <Button
            color="neutral"
            kind="secondary"
            size="small"
            type="button"
            className="min-w-0 flex-1"
            onClick={onNewChat}
          >
            <MessageSquarePlus size={16} />
            <Text kind="label/bold/md">New chat</Text>
          </Button>
          <Tooltip slotContent="Refresh history">
            <Button
              aria-label="Refresh history"
              kind="tertiary"
              size="small"
              type="button"
              disabled={isLoading}
              onClick={() => void refetch()}
            >
              <RefreshCw size={16} />
            </Button>
          </Tooltip>
        </Flex>
      </div>
      {error && (
        <div className="px-density-md py-density-sm">
          <Banner kind="inline" status="error">
            Could not load Claude history.
          </Banner>
        </div>
      )}
      {isLoading ? (
        <HistoryPanelSkeleton />
      ) : sessions.length ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {sessions.map((session) => (
            <HistorySessionButton
              key={session.session_id}
              active={session.session_id === activeSessionId}
              session={session}
              onSelect={() => onSelectSession(session.session_id)}
            />
          ))}
        </div>
      ) : !error ? (
        <Flex className="min-h-0 flex-1" align="center" justify="center">
          <Empty title="No chats yet" description="Claude Code sessions will appear here." />
        </Flex>
      ) : null}
    </>
  );
};
