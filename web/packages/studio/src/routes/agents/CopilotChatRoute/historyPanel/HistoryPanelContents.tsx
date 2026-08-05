// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Flex, Text, Tooltip } from '@nvidia/foundations-react-core';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { Empty } from '@studio/components/Empty';
import {
  deleteCopilotSessionHistory,
  getCopilotHistorySessionsQueryKey,
  listCopilotHistorySessions,
} from '@studio/routes/agents/CopilotChatRoute/api';
import { getHistorySessionTitle } from '@studio/routes/agents/CopilotChatRoute/historyPanel/helpers';
import { HistoryPanelSkeleton } from '@studio/routes/agents/CopilotChatRoute/historyPanel/HistoryPanelSkeletons';
import { HistorySessionButton } from '@studio/routes/agents/CopilotChatRoute/historyPanel/HistorySessionButton';
import type { CopilotHistoryPanelProps } from '@studio/routes/agents/CopilotChatRoute/historyPanel/types';
import type { CopilotHistorySession } from '@studio/routes/agents/CopilotChatRoute/types';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageSquarePlus, RefreshCw } from 'lucide-react';
import { useState } from 'react';

export const HistoryPanelContents = ({
  activeSessionId,
  onNewChat,
  onSelectSession,
  workspace = 'default',
}: CopilotHistoryPanelProps) => {
  const queryClient = useQueryClient();
  const [sessionToDelete, setSessionToDelete] = useState<CopilotHistorySession | null>(null);
  const historyQueryKey = getCopilotHistorySessionsQueryKey(workspace);
  const {
    data: sessions = [],
    error,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: historyQueryKey,
    queryFn: () => listCopilotHistorySessions(workspace),
    refetchOnMount: 'always',
  });

  const handleDelete = async (): Promise<boolean> => {
    if (!sessionToDelete) return false;
    const deletedSessionId = sessionToDelete.session_id;
    await deleteCopilotSessionHistory(deletedSessionId, workspace);
    await queryClient.invalidateQueries({ queryKey: historyQueryKey });
    if (deletedSessionId === activeSessionId) onNewChat();
    return true;
  };

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
            Could not load NeMo Copilot history.
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
              onDelete={() => setSessionToDelete(session)}
              onSelect={() => onSelectSession(session.session_id)}
            />
          ))}
        </div>
      ) : !error ? (
        <Flex className="min-h-0 flex-1" align="center" justify="center">
          <Empty title="No chats yet" description="NeMo Copilot sessions will appear here." />
        </Flex>
      ) : null}
      {sessionToDelete && (
        <DeleteConfirmationModal
          open
          title="Delete chat?"
          description={`Delete “${getHistorySessionTitle(sessionToDelete)}”? This chat cannot be recovered.`}
          successText="Chat deleted."
          errorText="Could not delete this chat."
          onClose={() => setSessionToDelete(null)}
          onDelete={handleDelete}
        />
      )}
    </>
  );
};
